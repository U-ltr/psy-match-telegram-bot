ALTER TABLE psychologists
ADD COLUMN IF NOT EXISTS help_topics JSONB DEFAULT '[]'::jsonb;

UPDATE psychologists
SET help_topics = specializations
WHERE (help_topics IS NULL OR help_topics = '[]'::jsonb)
  AND specializations IS NOT NULL;
