BEGIN;

-- =====================================================
-- SAFELY ADD ALL MISSING CONSTRAINTS AND COLUMNS
-- =====================================================

-- =====================================================
-- APP SCHEMA - GROUPS TABLE
-- =====================================================
SET search_path TO app, public;

-- First, identify and clean up duplicate groups
DO $$
DECLARE
    dup RECORD;
    affected_rows INTEGER;
BEGIN
    -- Create temp table to track duplicates
    CREATE TEMP TABLE duplicate_groups_temp AS
    SELECT user_id, group_name, array_agg(id ORDER BY id) as group_ids
    FROM groups
    GROUP BY user_id, group_name
    HAVING COUNT(*) > 1;

    -- Process each set of duplicates
    FOR dup IN SELECT * FROM duplicate_groups_temp LOOP
        -- Keep the oldest (lowest ID), delete the rest
        DELETE FROM groups 
        WHERE id = ANY(dup.group_ids[2:array_length(dup.group_ids, 1)]);
        
        GET DIAGNOSTICS affected_rows = ROW_COUNT;
        RAISE NOTICE 'Cleaned up duplicates for user % group "%": kept ID %, deleted % rows', 
            dup.user_id, dup.group_name, dup.group_ids[1], affected_rows;
    END LOOP;

    DROP TABLE duplicate_groups_temp;
END $$;

-- Now safely add the unique constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'unique_group_name_per_user'
    ) THEN
        ALTER TABLE groups
        ADD CONSTRAINT unique_group_name_per_user 
        UNIQUE (user_id, group_name);
        RAISE NOTICE 'Added unique_group_name_per_user constraint';
    ELSE
        RAISE NOTICE 'Constraint unique_group_name_per_user already exists';
    END IF;
END $$;

-- Create index for faster lookups (if not exists)
CREATE INDEX IF NOT EXISTS idx_groups_user_id ON groups(user_id);

-- =====================================================
-- APP SCHEMA - ACCOUNTS TABLE
-- =====================================================

-- First, identify and clean up duplicate accounts
DO $$
DECLARE
    dup RECORD;
    affected_rows INTEGER;
BEGIN
    -- Create temp table to track duplicate accounts
    CREATE TEMP TABLE duplicate_accounts_temp AS
    SELECT user_id, platform, account_username, array_agg(id ORDER BY id) as account_ids
    FROM accounts
    GROUP BY user_id, platform, account_username
    HAVING COUNT(*) > 1;

    -- Process each set of duplicates
    FOR dup IN SELECT * FROM duplicate_accounts_temp LOOP
        -- Keep the oldest (lowest ID), delete the rest
        DELETE FROM accounts 
        WHERE id = ANY(dup.account_ids[2:array_length(dup.account_ids, 1)]);
        
        GET DIAGNOSTICS affected_rows = ROW_COUNT;
        RAISE NOTICE 'Cleaned up duplicate account for user % % "%": kept ID %, deleted % rows', 
            dup.user_id, dup.platform, dup.account_username, dup.account_ids[1], affected_rows;
    END LOOP;

    DROP TABLE duplicate_accounts_temp;
END $$;

-- Add unique constraint for accounts
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'unique_account_per_user'
    ) THEN
        ALTER TABLE accounts
        ADD CONSTRAINT unique_account_per_user 
        UNIQUE (user_id, platform, account_username);
        RAISE NOTICE 'Added unique_account_per_user constraint';
    ELSE
        RAISE NOTICE 'Constraint unique_account_per_user already exists';
    END IF;
END $$;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_accounts_user_platform ON accounts(user_id, platform);

-- =====================================================
-- APP SCHEMA - PROXIES TABLE (add missing columns if any)
-- =====================================================

-- Add username and password columns if they don't exist
ALTER TABLE proxies
    ADD COLUMN IF NOT EXISTS username TEXT,
    ADD COLUMN IF NOT EXISTS password TEXT;

-- Add indexes for better proxy lookup performance (if not exists)
CREATE INDEX IF NOT EXISTS idx_proxies_user_active ON proxies(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_proxies_last_used ON proxies(last_used) WHERE is_active = TRUE;

-- =====================================================
-- AUTH SCHEMA - ENSURE ALL CONSTRAINTS EXIST
-- =====================================================
SET search_path TO auth, public;

-- Ensure users email is unique
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_email_key'
    ) THEN
        ALTER TABLE users
        ADD CONSTRAINT users_email_key UNIQUE (email);
        RAISE NOTICE 'Added users_email_key constraint';
    END IF;
END $$;

-- =====================================================
-- AUTH SCHEMA - SUBSCRIPTION PLANS
-- =====================================================

-- Ensure subscription_plans name is unique
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'subscription_plans_name_key'
    ) THEN
        ALTER TABLE subscription_plans
        ADD CONSTRAINT subscription_plans_name_key UNIQUE (name);
        RAISE NOTICE 'Added subscription_plans_name_key constraint';
    END IF;
END $$;

-- Seed plans if they don't exist (idempotent)
INSERT INTO subscription_plans
(name, max_channels, posts_per_day, comments_per_day, dms_per_day, price)
VALUES
('Tier 1', 3, 9, 9, 9, 1),
('Tier 2', 10, 30, 30, 30, 2),
('Tier 3', 100, 300, 300, 300, 3),
('Tier 4', 1000, 3000, 3000, 3000, 4),
('Tier 5 (Enterprise)', 10000, 30000, 30000, 30000, 5)
ON CONFLICT (name) DO NOTHING;

-- =====================================================
-- ADD FOREIGN KEY CONSTRAINTS IF MISSING
-- =====================================================
SET search_path TO app, auth, public;

-- User subscriptions foreign keys
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='user_subscriptions_user_fk') THEN
        ALTER TABLE user_subscriptions
        ADD CONSTRAINT user_subscriptions_user_fk
        FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added user_subscriptions_user_fk';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='user_subscriptions_plan_fk') THEN
        ALTER TABLE user_subscriptions
        ADD CONSTRAINT user_subscriptions_plan_fk
        FOREIGN KEY (plan_id) REFERENCES subscription_plans(id) ON DELETE RESTRICT;
        RAISE NOTICE 'Added user_subscriptions_plan_fk';
    END IF;
END $$;

-- Group accounts foreign keys
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='group_accounts_group_fk') THEN
        ALTER TABLE group_accounts
        ADD CONSTRAINT group_accounts_group_fk
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added group_accounts_group_fk';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='group_accounts_account_fk') THEN
        ALTER TABLE group_accounts
        ADD CONSTRAINT group_accounts_account_fk
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added group_accounts_account_fk';
    END IF;
END $$;

-- Tokens foreign key
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='tokens_account_fk') THEN
        ALTER TABLE tokens
        ADD CONSTRAINT tokens_account_fk
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added tokens_account_fk';
    END IF;
END $$;

-- Posts accounts foreign keys
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='posts_accounts_post_fk') THEN
        ALTER TABLE posts_accounts
        ADD CONSTRAINT posts_accounts_post_fk
        FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added posts_accounts_post_fk';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='posts_accounts_account_fk') THEN
        ALTER TABLE posts_accounts
        ADD CONSTRAINT posts_accounts_account_fk
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added posts_accounts_account_fk';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='posts_accounts_proxy_fk') THEN
        ALTER TABLE posts_accounts
        ADD CONSTRAINT posts_accounts_proxy_fk
        FOREIGN KEY (proxy_id) REFERENCES proxies(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added posts_accounts_proxy_fk';
    END IF;
END $$;

-- User timezones foreign key
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='user_timezones_user_fk') THEN
        ALTER TABLE user_timezones
        ADD CONSTRAINT user_timezones_user_fk
        FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added user_timezones_user_fk';
    END IF;
END $$;

-- =====================================================
-- MESSAGING SYSTEM FOREIGN KEYS
-- =====================================================

-- Conversation participants foreign keys
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='conversation_participants_conversation_fk') THEN
        ALTER TABLE conversation_participants
        ADD CONSTRAINT conversation_participants_conversation_fk
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added conversation_participants_conversation_fk';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='conversation_participants_user_fk') THEN
        ALTER TABLE conversation_participants
        ADD CONSTRAINT conversation_participants_user_fk
        FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added conversation_participants_user_fk';
    END IF;
END $$;

-- Messages foreign keys
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='messages_conversation_fk') THEN
        ALTER TABLE messages
        ADD CONSTRAINT messages_conversation_fk
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added messages_conversation_fk';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='messages_sender_fk') THEN
        ALTER TABLE messages
        ADD CONSTRAINT messages_sender_fk
        FOREIGN KEY (sender_id) REFERENCES auth.users(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added messages_sender_fk';
    END IF;
END $$;

-- Message read receipts foreign keys
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='message_read_receipts_message_fk') THEN
        ALTER TABLE message_read_receipts
        ADD CONSTRAINT message_read_receipts_message_fk
        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added message_read_receipts_message_fk';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='message_read_receipts_user_fk') THEN
        ALTER TABLE message_read_receipts
        ADD CONSTRAINT message_read_receipts_user_fk
        FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added message_read_receipts_user_fk';
    END IF;
END $$;

-- User presence foreign key
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='user_presence_user_fk') THEN
        ALTER TABLE user_presence
        ADD CONSTRAINT user_presence_user_fk
        FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added user_presence_user_fk';
    END IF;
END $$;

-- Message attachments foreign key
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='message_attachments_message_fk') THEN
        ALTER TABLE message_attachments
        ADD CONSTRAINT message_attachments_message_fk
        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added message_attachments_message_fk';
    END IF;
END $$;

-- =====================================================
-- FINAL VERIFICATION
-- =====================================================

-- Show all constraints added
SELECT 
    conname as constraint_name,
    conrelid::regclass as table_name
FROM pg_constraint
WHERE conname IN (
    'unique_group_name_per_user',
    'unique_account_per_user',
    'users_email_key',
    'subscription_plans_name_key',
    'user_subscriptions_user_fk',
    'user_subscriptions_plan_fk',
    'group_accounts_group_fk',
    'group_accounts_account_fk',
    'tokens_account_fk',
    'posts_accounts_post_fk',
    'posts_accounts_account_fk',
    'posts_accounts_proxy_fk',
    'user_timezones_user_fk',
    'conversation_participants_conversation_fk',
    'conversation_participants_user_fk',
    'messages_conversation_fk',
    'messages_sender_fk',
    'message_read_receipts_message_fk',
    'message_read_receipts_user_fk',
    'user_presence_user_fk',
    'message_attachments_message_fk'
)
ORDER BY table_name, constraint_name;

COMMIT;