-- Усиление журнала Telegram-публикаций.
--
-- Добавляет:
-- 1. счётчик контролируемых повторных попыток;
-- 2. время последней попытки;
-- 3. информацию о ручной проверке;
-- 4. запрет обычного DELETE из generated_posts.

ALTER TABLE generated_posts
    ADD COLUMN IF NOT EXISTS retry_count integer
        NOT NULL DEFAULT 0;

ALTER TABLE generated_posts
    ADD COLUMN IF NOT EXISTS last_attempt_at timestamptz;

ALTER TABLE generated_posts
    ADD COLUMN IF NOT EXISTS manual_reviewed_at timestamptz;

ALTER TABLE generated_posts
    ADD COLUMN IF NOT EXISTS manual_review_note text;


-- Для уже существующих публикаций считаем created_at
-- временем их первоначальной попытки отправки.
UPDATE generated_posts
SET last_attempt_at = created_at
WHERE last_attempt_at IS NULL;


-- PostgreSQL не поддерживает ADD CONSTRAINT IF NOT EXISTS
-- во всех нужных нам вариантах, поэтому проверяем системный каталог.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_generated_posts_retry_count'
          AND conrelid = 'generated_posts'::regclass
    ) THEN
        ALTER TABLE generated_posts
            ADD CONSTRAINT chk_generated_posts_retry_count
            CHECK (retry_count >= 0);
    END IF;
END;
$$;


-- Удалять строки из журнала публикаций запрещено.
--
-- Удаление строки фактически снимает защиту от дублей,
-- поэтому исправление состояний выполняется только через UPDATE.
CREATE OR REPLACE FUNCTION prevent_generated_posts_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'DELETE from generated_posts is disabled. Publication id=% must be resolved without deleting its history.',
        OLD.id
        USING
            ERRCODE = '55000',
            HINT = 'Use scripts/resolve_publication.py to inspect, mark sent, or retry an unknown publication.';
END;
$$;


DROP TRIGGER IF EXISTS trg_prevent_generated_posts_delete
    ON generated_posts;


CREATE TRIGGER trg_prevent_generated_posts_delete
BEFORE DELETE ON generated_posts
FOR EACH ROW
EXECUTE FUNCTION prevent_generated_posts_delete();