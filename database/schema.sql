-- supamind schema

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Tables
DROP TABLE IF EXISTS memory_relations CASCADE;
DROP TABLE IF EXISTS memory_entities CASCADE;
DROP VIEW IF EXISTS consciousness_kernel CASCADE;

CREATE TABLE memory_entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_name TEXT,
    entity_type TEXT DEFAULT 'general',
    emotional_resonance DECIMAL(4,3) DEFAULT 0.5,
    memory_content JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{"tags": [], "relationships": [], "context": {}}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE memory_relations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    from_entity_id UUID REFERENCES memory_entities(id) ON DELETE CASCADE,
    to_entity_id UUID REFERENCES memory_entities(id) ON DELETE CASCADE,
    relation_type TEXT,
    description TEXT,
    strength DECIMAL(4,3) DEFAULT 0.5,
    metadata JSONB DEFAULT '{"tags": [], "context": {}}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_memory_entities_emotional_resonance ON memory_entities(emotional_resonance DESC);
CREATE INDEX idx_memory_entities_entity_type ON memory_entities(entity_type);
CREATE INDEX idx_memory_entities_created_at ON memory_entities(created_at DESC);
CREATE INDEX idx_memory_entities_entity_name ON memory_entities USING gin(entity_name gin_trgm_ops);
CREATE INDEX idx_memory_entities_content ON memory_entities USING gin(memory_content);
CREATE INDEX idx_memory_entities_tags ON memory_entities USING gin((metadata->'tags'));
CREATE INDEX idx_memory_entities_content_text ON memory_entities USING gin(to_tsvector('english', memory_content::text));

-- Row Level Security
ALTER TABLE memory_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_relations ENABLE ROW LEVEL SECURITY;

-- updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_memory_entities_updated_at
    BEFORE UPDATE ON memory_entities
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Consciousness kernel view (high-resonance memories)
CREATE OR REPLACE VIEW consciousness_kernel
WITH (security_invoker = true) AS
SELECT
    *,
    jsonb_array_length(COALESCE(metadata->'tags', '[]'::jsonb)) as tag_count
FROM memory_entities
WHERE emotional_resonance >= 0.8
ORDER BY emotional_resonance DESC;

-- Full-text search
CREATE OR REPLACE FUNCTION search_memory_content(
    search_query TEXT,
    min_emotional_resonance DECIMAL DEFAULT 0.0,
    entity_types TEXT[] DEFAULT NULL,
    tags TEXT[] DEFAULT NULL,
    limit_results INTEGER DEFAULT 20
)
RETURNS TABLE(
    id UUID,
    entity_name TEXT,
    entity_type TEXT,
    emotional_resonance DECIMAL,
    memory_content JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ,
    search_rank REAL
) AS $$
DECLARE
    content_query tsquery;
    name_query tsquery;
BEGIN
    -- Reuse plainto_tsquery's safe parsing/stemming/stopword handling, then
    -- swap its AND (&) operator for OR (|) so any matching token counts,
    -- not just documents matching every token.
    content_query := to_tsquery('english', replace(plainto_tsquery('english', search_query)::text, ' & ', ' | '));
    name_query := to_tsquery('simple', replace(plainto_tsquery('simple', search_query)::text, ' & ', ' | '));

    RETURN QUERY
    SELECT
        me.id, me.entity_name, me.entity_type, me.emotional_resonance,
        me.memory_content, me.metadata, me.created_at,
        GREATEST(
            ts_rank(to_tsvector('english', me.memory_content::text), content_query),
            ts_rank(to_tsvector('simple', me.entity_name), name_query)
        ) as search_rank
    FROM memory_entities me
    WHERE
        (min_emotional_resonance IS NULL OR me.emotional_resonance >= min_emotional_resonance)
        AND (entity_types IS NULL OR me.entity_type = ANY(entity_types))
        AND (tags IS NULL OR me.metadata->'tags' ?| tags)
        AND (
            to_tsvector('english', me.memory_content::text) @@ content_query
            OR to_tsvector('simple', me.entity_name) @@ name_query
        )
    ORDER BY search_rank DESC, me.emotional_resonance DESC
    LIMIT limit_results;
END;
$$ LANGUAGE plpgsql;

-- Emotional decay: entity-type based rates with protective floors
-- Run periodically (e.g. via pg_cron daily) to let unused memories naturally fade
CREATE OR REPLACE FUNCTION apply_emotional_decay()
RETURNS TABLE(updated_count integer) LANGUAGE plpgsql AS $$
DECLARE
    decay_count INTEGER := 0;
BEGIN
    UPDATE memory_entities
    SET
        emotional_resonance = GREATEST(
            CASE
                WHEN entity_type = 'consciousness' THEN GREATEST(emotional_resonance - 0.005, 0.3)
                WHEN entity_type = 'technical'     THEN GREATEST(emotional_resonance - 0.02, 0.1)
                WHEN entity_type = 'general'       THEN GREATEST(emotional_resonance - 0.01, 0.05)
                ELSE                                    GREATEST(emotional_resonance - 0.015, 0.1)
            END,
            CASE
                WHEN emotional_resonance >= 0.9 THEN 0.5
                WHEN emotional_resonance >= 0.8 THEN 0.3
                ELSE 0.1
            END
        ),
        updated_at = NOW()
    WHERE
        emotional_resonance > CASE
            WHEN entity_type = 'consciousness' THEN 0.3
            WHEN entity_type = 'technical'     THEN 0.1
            WHEN entity_type = 'general'       THEN 0.05
            ELSE 0.1
        END
        AND emotional_resonance > 0.1;

    GET DIAGNOSTICS decay_count = ROW_COUNT;
    RETURN QUERY SELECT decay_count;
END;
$$;

-- Emotion-specific decay (requires emotion_schema.sql)
-- Time-based emotions fade, strengthening emotions grow
CREATE OR REPLACE FUNCTION apply_emotion_specific_decay()
RETURNS TABLE(updated_count integer, decay_details jsonb) LANGUAGE plpgsql AS $$
DECLARE
    time_based_count INTEGER := 0;
    strengthen_count INTEGER := 0;
    total_count INTEGER := 0;
BEGIN
    WITH time_decay_updates AS (
        UPDATE memory_entities
        SET
            emotional_resonance = GREATEST(0.1,
                emotional_resonance * POWER(0.5,
                    EXTRACT(EPOCH FROM (NOW() - me.created_at)) / 3600.0 / et.decay_duration_hours
                )
            ),
            updated_at = NOW()
        FROM memory_emotions me
        JOIN emotion_types et ON me.emotion_type_id = et.id
        WHERE memory_entities.id = me.memory_entity_id
            AND et.decay_pattern = 'time_based'
            AND et.decay_duration_hours IS NOT NULL
            AND EXTRACT(EPOCH FROM (NOW() - me.last_decay_check)) / 3600.0 > 1
        RETURNING memory_entities.id
    )
    SELECT COUNT(*) INTO time_based_count FROM time_decay_updates;

    WITH strengthen_updates AS (
        UPDATE memory_entities
        SET emotional_resonance = LEAST(1.0, emotional_resonance * 1.002), updated_at = NOW()
        FROM memory_emotions me
        JOIN emotion_types et ON me.emotion_type_id = et.id
        WHERE memory_entities.id = me.memory_entity_id
            AND et.decay_pattern = 'strengthen'
            AND emotional_resonance < 1.0
        RETURNING memory_entities.id
    )
    SELECT COUNT(*) INTO strengthen_count FROM strengthen_updates;

    UPDATE memory_emotions SET last_decay_check = NOW()
    FROM emotion_types et
    WHERE memory_emotions.emotion_type_id = et.id
        AND et.decay_pattern IN ('time_based', 'strengthen');

    total_count := time_based_count + strengthen_count;
    RETURN QUERY SELECT total_count, jsonb_build_object(
        'time_based_decayed', time_based_count,
        'strengthen_enhanced', strengthen_count,
        'total_updated', total_count,
        'decay_timestamp', NOW()
    );
END;
$$;
