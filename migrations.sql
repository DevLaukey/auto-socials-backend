BEGIN;

-- =====================================================
-- STEP 1: CREATE SCHEMAS
-- =====================================================

-- Create auth schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS auth;

-- Create app schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS app;

-- =====================================================
-- STEP 2: CREATE ALL TABLES (minimal version)
-- =====================================================

-- AUTH SCHEMA TABLES
SET search_path TO auth, public;

CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS subscription_plans (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS user_subscriptions (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS usage_counters (user_id INTEGER, platform TEXT, date DATE);
CREATE TABLE IF NOT EXISTS payment_intents (id UUID PRIMARY KEY);
CREATE TABLE IF NOT EXISTS payment_events (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS password_reset_tokens (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS post_payment_intents (id UUID PRIMARY KEY);
CREATE TABLE IF NOT EXISTS youtube_tokens (account_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS twitter_tokens (account_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS paypal_webhook_events (id SERIAL PRIMARY KEY);

-- APP SCHEMA TABLES
SET search_path TO app, public;

CREATE TABLE IF NOT EXISTS groups (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS proxies (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS accounts (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS posts (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS group_accounts (group_id INTEGER, account_id INTEGER);
CREATE TABLE IF NOT EXISTS tokens (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS posts_accounts (post_id INTEGER, account_id INTEGER);
CREATE TABLE IF NOT EXISTS user_timezones (user_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS clip_jobs (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS clips (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS comment_jobs (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS dm_jobs (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS dm_conversations (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS dm_messages (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS conversations (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS conversation_participants (conversation_id INTEGER, user_id INTEGER);
CREATE TABLE IF NOT EXISTS messages (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS message_read_receipts (id SERIAL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS user_presence (user_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS message_attachments (id SERIAL PRIMARY KEY);

-- =====================================================
-- STEP 3: ADD ALL COLUMNS TO ALL TABLES
-- =====================================================

-- AUTH SCHEMA COLUMNS
SET search_path TO auth, public;

-- users table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='email') THEN
        ALTER TABLE users ADD COLUMN email TEXT UNIQUE NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='password_hash') THEN
        ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='is_active') THEN
        ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='is_admin') THEN
        ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='disabled_at') THEN
        ALTER TABLE users ADD COLUMN disabled_at TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='created_at') THEN
        ALTER TABLE users ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- subscription_plans table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='subscription_plans' AND column_name='name') THEN
        ALTER TABLE subscription_plans ADD COLUMN name TEXT UNIQUE NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='subscription_plans' AND column_name='max_channels') THEN
        ALTER TABLE subscription_plans ADD COLUMN max_channels INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='subscription_plans' AND column_name='posts_per_day') THEN
        ALTER TABLE subscription_plans ADD COLUMN posts_per_day INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='subscription_plans' AND column_name='comments_per_day') THEN
        ALTER TABLE subscription_plans ADD COLUMN comments_per_day INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='subscription_plans' AND column_name='dms_per_day') THEN
        ALTER TABLE subscription_plans ADD COLUMN dms_per_day INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='subscription_plans' AND column_name='price') THEN
        ALTER TABLE subscription_plans ADD COLUMN price INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='subscription_plans' AND column_name='duration_days') THEN
        ALTER TABLE subscription_plans ADD COLUMN duration_days INTEGER NOT NULL DEFAULT 30;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='subscription_plans' AND column_name='created_at') THEN
        ALTER TABLE subscription_plans ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

-- user_subscriptions table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_subscriptions' AND column_name='user_id') THEN
        ALTER TABLE user_subscriptions ADD COLUMN user_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_subscriptions' AND column_name='plan_id') THEN
        ALTER TABLE user_subscriptions ADD COLUMN plan_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_subscriptions' AND column_name='start_date') THEN
        ALTER TABLE user_subscriptions ADD COLUMN start_date TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_subscriptions' AND column_name='end_date') THEN
        ALTER TABLE user_subscriptions ADD COLUMN end_date TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_subscriptions' AND column_name='is_active') THEN
        ALTER TABLE user_subscriptions ADD COLUMN is_active BOOLEAN DEFAULT TRUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_subscriptions' AND column_name='created_at') THEN
        ALTER TABLE user_subscriptions ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_subscriptions' AND column_name='updated_at') THEN
        ALTER TABLE user_subscriptions ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

-- usage_counters table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='usage_counters' AND column_name='user_id') THEN
        ALTER TABLE usage_counters ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='usage_counters' AND column_name='platform') THEN
        ALTER TABLE usage_counters ADD COLUMN platform TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='usage_counters' AND column_name='date') THEN
        ALTER TABLE usage_counters ADD COLUMN date DATE NOT NULL DEFAULT CURRENT_DATE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='usage_counters' AND column_name='posts') THEN
        ALTER TABLE usage_counters ADD COLUMN posts INTEGER DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='usage_counters' AND column_name='comments') THEN
        ALTER TABLE usage_counters ADD COLUMN comments INTEGER DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='usage_counters' AND column_name='dms') THEN
        ALTER TABLE usage_counters ADD COLUMN dms INTEGER DEFAULT 0;
    END IF;
END $$;

-- payment_intents table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_intents' AND column_name='user_id') THEN
        ALTER TABLE payment_intents ADD COLUMN user_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_intents' AND column_name='plan_id') THEN
        ALTER TABLE payment_intents ADD COLUMN plan_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_intents' AND column_name='amount') THEN
        ALTER TABLE payment_intents ADD COLUMN amount INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_intents' AND column_name='currency') THEN
        ALTER TABLE payment_intents ADD COLUMN currency TEXT DEFAULT 'KES';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_intents' AND column_name='status') THEN
        ALTER TABLE payment_intents ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_intents' AND column_name='zeroid_reference') THEN
        ALTER TABLE payment_intents ADD COLUMN zeroid_reference TEXT UNIQUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_intents' AND column_name='payment_method') THEN
        ALTER TABLE payment_intents ADD COLUMN payment_method TEXT DEFAULT 'zeroid';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_intents' AND column_name='paypal_order_id') THEN
        ALTER TABLE payment_intents ADD COLUMN paypal_order_id TEXT UNIQUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_intents' AND column_name='paypal_payer_id') THEN
        ALTER TABLE payment_intents ADD COLUMN paypal_payer_id TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_intents' AND column_name='paypal_payment_id') THEN
        ALTER TABLE payment_intents ADD COLUMN paypal_payment_id TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_intents' AND column_name='paypal_capture_id') THEN
        ALTER TABLE payment_intents ADD COLUMN paypal_capture_id TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_intents' AND column_name='created_at') THEN
        ALTER TABLE payment_intents ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_intents' AND column_name='updated_at') THEN
        ALTER TABLE payment_intents ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

-- payment_events table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_events' AND column_name='payment_intent_id') THEN
        ALTER TABLE payment_events ADD COLUMN payment_intent_id UUID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_events' AND column_name='event_type') THEN
        ALTER TABLE payment_events ADD COLUMN event_type TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_events' AND column_name='payload') THEN
        ALTER TABLE payment_events ADD COLUMN payload JSONB NOT NULL DEFAULT '{}';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payment_events' AND column_name='received_at') THEN
        ALTER TABLE payment_events ADD COLUMN received_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

-- password_reset_tokens table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='password_reset_tokens' AND column_name='user_id') THEN
        ALTER TABLE password_reset_tokens ADD COLUMN user_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='password_reset_tokens' AND column_name='token') THEN
        ALTER TABLE password_reset_tokens ADD COLUMN token TEXT NOT NULL UNIQUE DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='password_reset_tokens' AND column_name='expires_at') THEN
        ALTER TABLE password_reset_tokens ADD COLUMN expires_at TIMESTAMP NOT NULL DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='password_reset_tokens' AND column_name='used') THEN
        ALTER TABLE password_reset_tokens ADD COLUMN used BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='password_reset_tokens' AND column_name='created_at') THEN
        ALTER TABLE password_reset_tokens ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- post_payment_intents table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='post_payment_intents' AND column_name='user_id') THEN
        ALTER TABLE post_payment_intents ADD COLUMN user_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='post_payment_intents' AND column_name='post_data') THEN
        ALTER TABLE post_payment_intents ADD COLUMN post_data JSONB NOT NULL DEFAULT '{}';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='post_payment_intents' AND column_name='amount') THEN
        ALTER TABLE post_payment_intents ADD COLUMN amount INTEGER NOT NULL DEFAULT 100;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='post_payment_intents' AND column_name='currency') THEN
        ALTER TABLE post_payment_intents ADD COLUMN currency TEXT DEFAULT 'KES';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='post_payment_intents' AND column_name='status') THEN
        ALTER TABLE post_payment_intents ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='post_payment_intents' AND column_name='zeroid_reference') THEN
        ALTER TABLE post_payment_intents ADD COLUMN zeroid_reference TEXT UNIQUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='post_payment_intents' AND column_name='payment_method') THEN
        ALTER TABLE post_payment_intents ADD COLUMN payment_method TEXT DEFAULT 'zeroid';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='post_payment_intents' AND column_name='paypal_order_id') THEN
        ALTER TABLE post_payment_intents ADD COLUMN paypal_order_id TEXT UNIQUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='post_payment_intents' AND column_name='paypal_payer_id') THEN
        ALTER TABLE post_payment_intents ADD COLUMN paypal_payer_id TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='post_payment_intents' AND column_name='paypal_payment_id') THEN
        ALTER TABLE post_payment_intents ADD COLUMN paypal_payment_id TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='post_payment_intents' AND column_name='paypal_capture_id') THEN
        ALTER TABLE post_payment_intents ADD COLUMN paypal_capture_id TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='post_payment_intents' AND column_name='created_at') THEN
        ALTER TABLE post_payment_intents ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='post_payment_intents' AND column_name='updated_at') THEN
        ALTER TABLE post_payment_intents ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

-- youtube_tokens table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='youtube_tokens' AND column_name='account_id') THEN
        ALTER TABLE youtube_tokens ADD COLUMN account_id INTEGER PRIMARY KEY;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='youtube_tokens' AND column_name='token_json') THEN
        ALTER TABLE youtube_tokens ADD COLUMN token_json JSONB NOT NULL DEFAULT '{}';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='youtube_tokens' AND column_name='updated_at') THEN
        ALTER TABLE youtube_tokens ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

-- twitter_tokens table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='twitter_tokens' AND column_name='account_id') THEN
        ALTER TABLE twitter_tokens ADD COLUMN account_id INTEGER PRIMARY KEY;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='twitter_tokens' AND column_name='access_token') THEN
        ALTER TABLE twitter_tokens ADD COLUMN access_token TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='twitter_tokens' AND column_name='refresh_token') THEN
        ALTER TABLE twitter_tokens ADD COLUMN refresh_token TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='twitter_tokens' AND column_name='expires_at') THEN
        ALTER TABLE twitter_tokens ADD COLUMN expires_at TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='twitter_tokens' AND column_name='token_type') THEN
        ALTER TABLE twitter_tokens ADD COLUMN token_type TEXT DEFAULT 'bearer';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='twitter_tokens' AND column_name='scope') THEN
        ALTER TABLE twitter_tokens ADD COLUMN scope TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='twitter_tokens' AND column_name='updated_at') THEN
        ALTER TABLE twitter_tokens ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

-- paypal_webhook_events table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='paypal_webhook_events' AND column_name='event_id') THEN
        ALTER TABLE paypal_webhook_events ADD COLUMN event_id TEXT UNIQUE NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='paypal_webhook_events' AND column_name='event_type') THEN
        ALTER TABLE paypal_webhook_events ADD COLUMN event_type TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='paypal_webhook_events' AND column_name='resource_type') THEN
        ALTER TABLE paypal_webhook_events ADD COLUMN resource_type TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='paypal_webhook_events' AND column_name='resource_id') THEN
        ALTER TABLE paypal_webhook_events ADD COLUMN resource_id TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='paypal_webhook_events' AND column_name='resource') THEN
        ALTER TABLE paypal_webhook_events ADD COLUMN resource JSONB;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='paypal_webhook_events' AND column_name='summary') THEN
        ALTER TABLE paypal_webhook_events ADD COLUMN summary TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='paypal_webhook_events' AND column_name='created_at') THEN
        ALTER TABLE paypal_webhook_events ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='paypal_webhook_events' AND column_name='processed') THEN
        ALTER TABLE paypal_webhook_events ADD COLUMN processed BOOLEAN DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='paypal_webhook_events' AND column_name='processed_at') THEN
        ALTER TABLE paypal_webhook_events ADD COLUMN processed_at TIMESTAMPTZ;
    END IF;
END $$;

-- APP SCHEMA COLUMNS
SET search_path TO app, public;

-- groups table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='groups' AND column_name='group_name') THEN
        ALTER TABLE groups ADD COLUMN group_name TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='groups' AND column_name='user_id') THEN
        ALTER TABLE groups ADD COLUMN user_id INTEGER;
    END IF;
END $$;

-- proxies table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proxies' AND column_name='user_id') THEN
        ALTER TABLE proxies ADD COLUMN user_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proxies' AND column_name='proxy_address') THEN
        ALTER TABLE proxies ADD COLUMN proxy_address TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proxies' AND column_name='proxy_type') THEN
        ALTER TABLE proxies ADD COLUMN proxy_type TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proxies' AND column_name='username') THEN
        ALTER TABLE proxies ADD COLUMN username TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proxies' AND column_name='password') THEN
        ALTER TABLE proxies ADD COLUMN password TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proxies' AND column_name='is_active') THEN
        ALTER TABLE proxies ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proxies' AND column_name='last_used') THEN
        ALTER TABLE proxies ADD COLUMN last_used TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proxies' AND column_name='fail_count') THEN
        ALTER TABLE proxies ADD COLUMN fail_count INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proxies' AND column_name='created_at') THEN
        ALTER TABLE proxies ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- accounts table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='accounts' AND column_name='user_id') THEN
        ALTER TABLE accounts ADD COLUMN user_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='accounts' AND column_name='platform') THEN
        ALTER TABLE accounts ADD COLUMN platform TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='accounts' AND column_name='account_username') THEN
        ALTER TABLE accounts ADD COLUMN account_username TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='accounts' AND column_name='password') THEN
        ALTER TABLE accounts ADD COLUMN password TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='accounts' AND column_name='session_data') THEN
        ALTER TABLE accounts ADD COLUMN session_data TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='accounts' AND column_name='status') THEN
        ALTER TABLE accounts ADD COLUMN status TEXT DEFAULT 'active';
    END IF;
END $$;

-- posts table columns (all of them)
DO $$
BEGIN
    -- Basic fields
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='user_id') THEN
        ALTER TABLE posts ADD COLUMN user_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='account_id') THEN
        ALTER TABLE posts ADD COLUMN account_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='media_file') THEN
        ALTER TABLE posts ADD COLUMN media_file TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='title') THEN
        ALTER TABLE posts ADD COLUMN title TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='description') THEN
        ALTER TABLE posts ADD COLUMN description TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='hashtags') THEN
        ALTER TABLE posts ADD COLUMN hashtags TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='tags') THEN
        ALTER TABLE posts ADD COLUMN tags TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='privacy_status') THEN
        ALTER TABLE posts ADD COLUMN privacy_status TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='scheduled_time') THEN
        ALTER TABLE posts ADD COLUMN scheduled_time TIMESTAMP WITH TIME ZONE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='status') THEN
        ALTER TABLE posts ADD COLUMN status TEXT NOT NULL DEFAULT 'Pending';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='created_at') THEN
        ALTER TABLE posts ADD COLUMN created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='post_type') THEN
        ALTER TABLE posts ADD COLUMN post_type TEXT DEFAULT 'feed';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='cover_image') THEN
        ALTER TABLE posts ADD COLUMN cover_image TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='audio_name') THEN
        ALTER TABLE posts ADD COLUMN audio_name TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='location') THEN
        ALTER TABLE posts ADD COLUMN location TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='disable_comments') THEN
        ALTER TABLE posts ADD COLUMN disable_comments BOOLEAN DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='share_to_feed') THEN
        ALTER TABLE posts ADD COLUMN share_to_feed BOOLEAN DEFAULT TRUE;
    END IF;
    
    -- Analytics fields
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='likes') THEN
        ALTER TABLE posts ADD COLUMN likes INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='comments') THEN
        ALTER TABLE posts ADD COLUMN comments INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='views') THEN
        ALTER TABLE posts ADD COLUMN views INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='shares') THEN
        ALTER TABLE posts ADD COLUMN shares INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='error_message') THEN
        ALTER TABLE posts ADD COLUMN error_message TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='youtube_video_id') THEN
        ALTER TABLE posts ADD COLUMN youtube_video_id TEXT;
    END IF;
    
    -- Twitter/X specific columns
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='tweet_id') THEN
        ALTER TABLE posts ADD COLUMN tweet_id TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='media_ids') THEN
        ALTER TABLE posts ADD COLUMN media_ids JSONB;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='reply_to_tweet_id') THEN
        ALTER TABLE posts ADD COLUMN reply_to_tweet_id TEXT;
    END IF;
    
    -- AI engagement columns
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='campaign_id') THEN
        ALTER TABLE posts ADD COLUMN campaign_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='ai_comment_enabled') THEN
        ALTER TABLE posts ADD COLUMN ai_comment_enabled BOOLEAN DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='ai_comment_count') THEN
        ALTER TABLE posts ADD COLUMN ai_comment_count INTEGER DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='ai_comment_style') THEN
        ALTER TABLE posts ADD COLUMN ai_comment_style TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='ai_comments_delay_minutes') THEN
        ALTER TABLE posts ADD COLUMN ai_comments_delay_minutes INTEGER DEFAULT 10;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='ai_dms_enabled') THEN
        ALTER TABLE posts ADD COLUMN ai_dms_enabled BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- group_accounts table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='group_accounts' AND column_name='group_id') THEN
        ALTER TABLE group_accounts ADD COLUMN group_id INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='group_accounts' AND column_name='account_id') THEN
        ALTER TABLE group_accounts ADD COLUMN account_id INTEGER NOT NULL DEFAULT 0;
    END IF;
END $$;

-- tokens table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tokens' AND column_name='account_id') THEN
        ALTER TABLE tokens ADD COLUMN account_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tokens' AND column_name='access_token') THEN
        ALTER TABLE tokens ADD COLUMN access_token TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tokens' AND column_name='refresh_token') THEN
        ALTER TABLE tokens ADD COLUMN refresh_token TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tokens' AND column_name='expires_at') THEN
        ALTER TABLE tokens ADD COLUMN expires_at BIGINT NOT NULL DEFAULT 0;
    END IF;
END $$;

-- posts_accounts table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts_accounts' AND column_name='post_id') THEN
        ALTER TABLE posts_accounts ADD COLUMN post_id INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts_accounts' AND column_name='account_id') THEN
        ALTER TABLE posts_accounts ADD COLUMN account_id INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts_accounts' AND column_name='proxy_id') THEN
        ALTER TABLE posts_accounts ADD COLUMN proxy_id INTEGER;
    END IF;
END $$;

-- user_timezones table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_timezones' AND column_name='user_id') THEN
        ALTER TABLE user_timezones ADD COLUMN user_id INTEGER PRIMARY KEY;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_timezones' AND column_name='timezone') THEN
        ALTER TABLE user_timezones ADD COLUMN timezone TEXT NOT NULL DEFAULT 'UTC';
    END IF;
END $$;

-- clip_jobs table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_jobs' AND column_name='user_id') THEN
        ALTER TABLE clip_jobs ADD COLUMN user_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_jobs' AND column_name='source_url') THEN
        ALTER TABLE clip_jobs ADD COLUMN source_url TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_jobs' AND column_name='local_video_path') THEN
        ALTER TABLE clip_jobs ADD COLUMN local_video_path TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_jobs' AND column_name='clip_length') THEN
        ALTER TABLE clip_jobs ADD COLUMN clip_length INTEGER DEFAULT 30;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_jobs' AND column_name='max_clips') THEN
        ALTER TABLE clip_jobs ADD COLUMN max_clips INTEGER DEFAULT 3;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_jobs' AND column_name='style') THEN
        ALTER TABLE clip_jobs ADD COLUMN style TEXT DEFAULT 'highlight';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_jobs' AND column_name='status') THEN
        ALTER TABLE clip_jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_jobs' AND column_name='progress') THEN
        ALTER TABLE clip_jobs ADD COLUMN progress INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_jobs' AND column_name='error') THEN
        ALTER TABLE clip_jobs ADD COLUMN error TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_jobs' AND column_name='created_at') THEN
        ALTER TABLE clip_jobs ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- clips table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clips' AND column_name='clip_job_id') THEN
        ALTER TABLE clips ADD COLUMN clip_job_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clips' AND column_name='file_path') THEN
        ALTER TABLE clips ADD COLUMN file_path TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clips' AND column_name='duration') THEN
        ALTER TABLE clips ADD COLUMN duration INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clips' AND column_name='created_at') THEN
        ALTER TABLE clips ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- comment_jobs table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='user_id') THEN
        ALTER TABLE comment_jobs ADD COLUMN user_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='campaign_id') THEN
        ALTER TABLE comment_jobs ADD COLUMN campaign_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='post_id') THEN
        ALTER TABLE comment_jobs ADD COLUMN post_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='account_id') THEN
        ALTER TABLE comment_jobs ADD COLUMN account_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='target_url') THEN
        ALTER TABLE comment_jobs ADD COLUMN target_url TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='comment_text') THEN
        ALTER TABLE comment_jobs ADD COLUMN comment_text TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='status') THEN
        ALTER TABLE comment_jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='attempts') THEN
        ALTER TABLE comment_jobs ADD COLUMN attempts INTEGER DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='max_attempts') THEN
        ALTER TABLE comment_jobs ADD COLUMN max_attempts INTEGER DEFAULT 3;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='error_message') THEN
        ALTER TABLE comment_jobs ADD COLUMN error_message TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='scheduled_time') THEN
        ALTER TABLE comment_jobs ADD COLUMN scheduled_time TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='executed_time') THEN
        ALTER TABLE comment_jobs ADD COLUMN executed_time TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='created_at') THEN
        ALTER TABLE comment_jobs ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='comment_jobs' AND column_name='updated_at') THEN
        ALTER TABLE comment_jobs ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- dm_jobs table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='user_id') THEN
        ALTER TABLE dm_jobs ADD COLUMN user_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='campaign_id') THEN
        ALTER TABLE dm_jobs ADD COLUMN campaign_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='account_id') THEN
        ALTER TABLE dm_jobs ADD COLUMN account_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='recipient_username') THEN
        ALTER TABLE dm_jobs ADD COLUMN recipient_username TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='message_text') THEN
        ALTER TABLE dm_jobs ADD COLUMN message_text TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='status') THEN
        ALTER TABLE dm_jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='attempts') THEN
        ALTER TABLE dm_jobs ADD COLUMN attempts INTEGER DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='max_attempts') THEN
        ALTER TABLE dm_jobs ADD COLUMN max_attempts INTEGER DEFAULT 3;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='error_message') THEN
        ALTER TABLE dm_jobs ADD COLUMN error_message TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='scheduled_time') THEN
        ALTER TABLE dm_jobs ADD COLUMN scheduled_time TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='executed_time') THEN
        ALTER TABLE dm_jobs ADD COLUMN executed_time TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='created_at') THEN
        ALTER TABLE dm_jobs ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='updated_at') THEN
        ALTER TABLE dm_jobs ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_jobs' AND column_name='post_id') THEN
        ALTER TABLE dm_jobs ADD COLUMN post_id INTEGER;
    END IF;
END $$;

-- dm_conversations table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_conversations' AND column_name='account_id') THEN
        ALTER TABLE dm_conversations ADD COLUMN account_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_conversations' AND column_name='recipient_username') THEN
        ALTER TABLE dm_conversations ADD COLUMN recipient_username TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_conversations' AND column_name='last_message_at') THEN
        ALTER TABLE dm_conversations ADD COLUMN last_message_at TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_conversations' AND column_name='context') THEN
        ALTER TABLE dm_conversations ADD COLUMN context JSONB DEFAULT '{}';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_conversations' AND column_name='created_at') THEN
        ALTER TABLE dm_conversations ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- dm_messages table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_messages' AND column_name='conversation_id') THEN
        ALTER TABLE dm_messages ADD COLUMN conversation_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_messages' AND column_name='content') THEN
        ALTER TABLE dm_messages ADD COLUMN content TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_messages' AND column_name='is_from_me') THEN
        ALTER TABLE dm_messages ADD COLUMN is_from_me BOOLEAN DEFAULT TRUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_messages' AND column_name='ai_generated') THEN
        ALTER TABLE dm_messages ADD COLUMN ai_generated BOOLEAN DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dm_messages' AND column_name='created_at') THEN
        ALTER TABLE dm_messages ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- conversations table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='conversations' AND column_name='title') THEN
        ALTER TABLE conversations ADD COLUMN title TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='conversations' AND column_name='created_at') THEN
        ALTER TABLE conversations ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='conversations' AND column_name='last_message_at') THEN
        ALTER TABLE conversations ADD COLUMN last_message_at TIMESTAMPTZ;
    END IF;
END $$;

-- conversation_participants table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='conversation_participants' AND column_name='conversation_id') THEN
        ALTER TABLE conversation_participants ADD COLUMN conversation_id INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='conversation_participants' AND column_name='user_id') THEN
        ALTER TABLE conversation_participants ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='conversation_participants' AND column_name='joined_at') THEN
        ALTER TABLE conversation_participants ADD COLUMN joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- messages table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='messages' AND column_name='conversation_id') THEN
        ALTER TABLE messages ADD COLUMN conversation_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='messages' AND column_name='sender_id') THEN
        ALTER TABLE messages ADD COLUMN sender_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='messages' AND column_name='content') THEN
        ALTER TABLE messages ADD COLUMN content TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='messages' AND column_name='created_at') THEN
        ALTER TABLE messages ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='messages' AND column_name='is_read') THEN
        ALTER TABLE messages ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END $$;

-- message_read_receipts table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='message_read_receipts' AND column_name='message_id') THEN
        ALTER TABLE message_read_receipts ADD COLUMN message_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='message_read_receipts' AND column_name='user_id') THEN
        ALTER TABLE message_read_receipts ADD COLUMN user_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='message_read_receipts' AND column_name='read_at') THEN
        ALTER TABLE message_read_receipts ADD COLUMN read_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- user_presence table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_presence' AND column_name='user_id') THEN
        ALTER TABLE user_presence ADD COLUMN user_id INTEGER PRIMARY KEY;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_presence' AND column_name='status') THEN
        ALTER TABLE user_presence ADD COLUMN status TEXT NOT NULL DEFAULT 'offline';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_presence' AND column_name='last_seen_at') THEN
        ALTER TABLE user_presence ADD COLUMN last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_presence' AND column_name='custom_status') THEN
        ALTER TABLE user_presence ADD COLUMN custom_status TEXT;
    END IF;
END $$;

-- message_attachments table columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='message_attachments' AND column_name='message_id') THEN
        ALTER TABLE message_attachments ADD COLUMN message_id INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='message_attachments' AND column_name='file_name') THEN
        ALTER TABLE message_attachments ADD COLUMN file_name TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='message_attachments' AND column_name='file_size') THEN
        ALTER TABLE message_attachments ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='message_attachments' AND column_name='mime_type') THEN
        ALTER TABLE message_attachments ADD COLUMN mime_type TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='message_attachments' AND column_name='storage_path') THEN
        ALTER TABLE message_attachments ADD COLUMN storage_path TEXT NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='message_attachments' AND column_name='created_at') THEN
        ALTER TABLE message_attachments ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- =====================================================
-- STEP 4: ADD ALL CONSTRAINTS (Foreign Keys, Unique, Primary Keys)
-- =====================================================

-- Add primary keys and unique constraints
DO $$
BEGIN
    -- users constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='users_email_key') THEN
        ALTER TABLE auth.users ADD CONSTRAINT users_email_key UNIQUE (email);
    END IF;
    
    -- subscription_plans constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='subscription_plans_name_key') THEN
        ALTER TABLE auth.subscription_plans ADD CONSTRAINT subscription_plans_name_key UNIQUE (name);
    END IF;
    
    -- group_accounts primary key
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='group_accounts_pkey') THEN
        ALTER TABLE app.group_accounts ADD PRIMARY KEY (group_id, account_id);
    END IF;
    
    -- posts_accounts primary key
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='posts_accounts_pkey') THEN
        ALTER TABLE app.posts_accounts ADD PRIMARY KEY (post_id, account_id);
    END IF;
    
    -- usage_counters primary key
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='usage_counters_pkey') THEN
        ALTER TABLE auth.usage_counters ADD PRIMARY KEY (user_id, platform, date);
    END IF;
    
    -- dm_conversations unique constraint
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='dm_conversations_account_id_recipient_username_key') THEN
        ALTER TABLE app.dm_conversations ADD UNIQUE (account_id, recipient_username);
    END IF;
    
    -- conversation_participants primary key
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='conversation_participants_pkey') THEN
        ALTER TABLE app.conversation_participants ADD PRIMARY KEY (conversation_id, user_id);
    END IF;
    
    -- message_read_receipts unique constraint
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='message_read_receipts_message_id_user_id_key') THEN
        ALTER TABLE app.message_read_receipts ADD UNIQUE (message_id, user_id);
    END IF;
    
    -- paypal_webhook_events unique constraint
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='paypal_webhook_events_event_id_key') THEN
        ALTER TABLE auth.paypal_webhook_events ADD CONSTRAINT paypal_webhook_events_event_id_key UNIQUE (event_id);
    END IF;
END $$;

-- Add all foreign key constraints
DO $$
BEGIN
    -- groups foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='groups_user_id_fkey') THEN
        ALTER TABLE app.groups ADD CONSTRAINT groups_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    
    -- proxies foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='proxies_user_id_fkey') THEN
        ALTER TABLE app.proxies ADD CONSTRAINT proxies_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    
    -- accounts foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='accounts_user_id_fkey') THEN
        ALTER TABLE app.accounts ADD CONSTRAINT accounts_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    
    -- posts foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='posts_user_id_fkey') THEN
        ALTER TABLE app.posts ADD CONSTRAINT posts_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='posts_account_id_fkey') THEN
        ALTER TABLE app.posts ADD CONSTRAINT posts_account_id_fkey FOREIGN KEY (account_id) REFERENCES app.accounts(id) ON DELETE CASCADE;
    END IF;
    
    -- group_accounts foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='group_accounts_group_id_fkey') THEN
        ALTER TABLE app.group_accounts ADD CONSTRAINT group_accounts_group_id_fkey FOREIGN KEY (group_id) REFERENCES app.groups(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='group_accounts_account_id_fkey') THEN
        ALTER TABLE app.group_accounts ADD CONSTRAINT group_accounts_account_id_fkey FOREIGN KEY (account_id) REFERENCES app.accounts(id) ON DELETE CASCADE;
    END IF;
    
    -- tokens foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='tokens_account_id_fkey') THEN
        ALTER TABLE app.tokens ADD CONSTRAINT tokens_account_id_fkey FOREIGN KEY (account_id) REFERENCES app.accounts(id) ON DELETE CASCADE;
    END IF;
    
    -- posts_accounts foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='posts_accounts_post_id_fkey') THEN
        ALTER TABLE app.posts_accounts ADD CONSTRAINT posts_accounts_post_id_fkey FOREIGN KEY (post_id) REFERENCES app.posts(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='posts_accounts_account_id_fkey') THEN
        ALTER TABLE app.posts_accounts ADD CONSTRAINT posts_accounts_account_id_fkey FOREIGN KEY (account_id) REFERENCES app.accounts(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='posts_accounts_proxy_id_fkey') THEN
        ALTER TABLE app.posts_accounts ADD CONSTRAINT posts_accounts_proxy_id_fkey FOREIGN KEY (proxy_id) REFERENCES app.proxies(id) ON DELETE SET NULL;
    END IF;
    
    -- user_timezones foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='user_timezones_user_id_fkey') THEN
        ALTER TABLE app.user_timezones ADD CONSTRAINT user_timezones_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    
    -- clip_jobs foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='clip_jobs_user_id_fkey') THEN
        ALTER TABLE app.clip_jobs ADD CONSTRAINT clip_jobs_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    
    -- clips foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='clips_clip_job_id_fkey') THEN
        ALTER TABLE app.clips ADD CONSTRAINT clips_clip_job_id_fkey FOREIGN KEY (clip_job_id) REFERENCES app.clip_jobs(id) ON DELETE CASCADE;
    END IF;
    
    -- comment_jobs foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='comment_jobs_user_id_fkey') THEN
        ALTER TABLE app.comment_jobs ADD CONSTRAINT comment_jobs_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='comment_jobs_post_id_fkey') THEN
        ALTER TABLE app.comment_jobs ADD CONSTRAINT comment_jobs_post_id_fkey FOREIGN KEY (post_id) REFERENCES app.posts(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='comment_jobs_account_id_fkey') THEN
        ALTER TABLE app.comment_jobs ADD CONSTRAINT comment_jobs_account_id_fkey FOREIGN KEY (account_id) REFERENCES app.accounts(id) ON DELETE CASCADE;
    END IF;
    
    -- dm_jobs foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='dm_jobs_user_id_fkey') THEN
        ALTER TABLE app.dm_jobs ADD CONSTRAINT dm_jobs_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='dm_jobs_account_id_fkey') THEN
        ALTER TABLE app.dm_jobs ADD CONSTRAINT dm_jobs_account_id_fkey FOREIGN KEY (account_id) REFERENCES app.accounts(id) ON DELETE CASCADE;
    END IF;
    
    -- dm_conversations foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='dm_conversations_account_id_fkey') THEN
        ALTER TABLE app.dm_conversations ADD CONSTRAINT dm_conversations_account_id_fkey FOREIGN KEY (account_id) REFERENCES app.accounts(id) ON DELETE CASCADE;
    END IF;
    
    -- dm_messages foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='dm_messages_conversation_id_fkey') THEN
        ALTER TABLE app.dm_messages ADD CONSTRAINT dm_messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES app.dm_conversations(id) ON DELETE CASCADE;
    END IF;
    
    -- conversation_participants foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='conversation_participants_conversation_id_fkey') THEN
        ALTER TABLE app.conversation_participants ADD CONSTRAINT conversation_participants_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES app.conversations(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='conversation_participants_user_id_fkey') THEN
        ALTER TABLE app.conversation_participants ADD CONSTRAINT conversation_participants_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    
    -- messages foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='messages_conversation_id_fkey') THEN
        ALTER TABLE app.messages ADD CONSTRAINT messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES app.conversations(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='messages_sender_id_fkey') THEN
        ALTER TABLE app.messages ADD CONSTRAINT messages_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    
    -- message_read_receipts foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='message_read_receipts_message_id_fkey') THEN
        ALTER TABLE app.message_read_receipts ADD CONSTRAINT message_read_receipts_message_id_fkey FOREIGN KEY (message_id) REFERENCES app.messages(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='message_read_receipts_user_id_fkey') THEN
        ALTER TABLE app.message_read_receipts ADD CONSTRAINT message_read_receipts_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    
    -- user_presence foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='user_presence_user_id_fkey') THEN
        ALTER TABLE app.user_presence ADD CONSTRAINT user_presence_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    
    -- message_attachments foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='message_attachments_message_id_fkey') THEN
        ALTER TABLE app.message_attachments ADD CONSTRAINT message_attachments_message_id_fkey FOREIGN KEY (message_id) REFERENCES app.messages(id) ON DELETE CASCADE;
    END IF;
    
    -- user_subscriptions foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='user_subscriptions_user_id_fkey') THEN
        ALTER TABLE auth.user_subscriptions ADD CONSTRAINT user_subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='user_subscriptions_plan_id_fkey') THEN
        ALTER TABLE auth.user_subscriptions ADD CONSTRAINT user_subscriptions_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES auth.subscription_plans(id) ON DELETE RESTRICT;
    END IF;
    
    -- payment_intents foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='payment_intents_user_id_fkey') THEN
        ALTER TABLE auth.payment_intents ADD CONSTRAINT payment_intents_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='payment_intents_plan_id_fkey') THEN
        ALTER TABLE auth.payment_intents ADD CONSTRAINT payment_intents_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES auth.subscription_plans(id) ON DELETE RESTRICT;
    END IF;
    
    -- payment_events foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='payment_events_payment_intent_id_fkey') THEN
        ALTER TABLE auth.payment_events ADD CONSTRAINT payment_events_payment_intent_id_fkey FOREIGN KEY (payment_intent_id) REFERENCES auth.payment_intents(id) ON DELETE CASCADE;
    END IF;
    
    -- password_reset_tokens foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='password_reset_tokens_user_id_fkey') THEN
        ALTER TABLE auth.password_reset_tokens ADD CONSTRAINT password_reset_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    
    -- post_payment_intents foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='post_payment_intents_user_id_fkey') THEN
        ALTER TABLE auth.post_payment_intents ADD CONSTRAINT post_payment_intents_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    
    -- youtube_tokens foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='youtube_tokens_account_id_fkey') THEN
        -- Remove orphaned rows that would violate the constraint
        DELETE FROM auth.youtube_tokens WHERE account_id NOT IN (SELECT id FROM app.accounts);
        ALTER TABLE auth.youtube_tokens ADD CONSTRAINT youtube_tokens_account_id_fkey FOREIGN KEY (account_id) REFERENCES app.accounts(id) ON DELETE CASCADE;
    END IF;

    -- twitter_tokens foreign keys
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='twitter_tokens_account_id_fkey') THEN
        -- Remove orphaned rows that would violate the constraint
        DELETE FROM auth.twitter_tokens WHERE account_id NOT IN (SELECT id FROM app.accounts);
        ALTER TABLE auth.twitter_tokens ADD CONSTRAINT twitter_tokens_account_id_fkey FOREIGN KEY (account_id) REFERENCES app.accounts(id) ON DELETE CASCADE;
    END IF;
END $$;

-- =====================================================
-- STEP 5: SEED INITIAL DATA
-- =====================================================

-- Seed subscription plans
INSERT INTO auth.subscription_plans
    (name, max_channels, posts_per_day, comments_per_day, dms_per_day, price)
VALUES
    ('Tier 1', 3, 9, 9, 9, 1),
    ('Tier 2', 10, 30, 30, 30, 2),
    ('Tier 3', 100, 300, 300, 300, 3),
    ('Tier 4', 1000, 3000, 3000, 3000, 4),
    ('Tier 5 (Enterprise)', 10000, 30000, 30000, 30000, 5)
ON CONFLICT (name) DO NOTHING;

-- =====================================================
-- STEP 6: CREATE INDEXES
-- =====================================================
SET search_path TO app, public;

-- Groups indexes
CREATE INDEX IF NOT EXISTS idx_groups_user_id ON groups(user_id);

-- Accounts indexes
CREATE INDEX IF NOT EXISTS idx_accounts_user_platform ON accounts(user_id, platform);

-- Proxies indexes
CREATE INDEX IF NOT EXISTS idx_proxies_user_active ON proxies(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_proxies_last_used ON proxies(last_used) WHERE is_active = TRUE;

-- Posts indexes (check if columns exist)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='youtube_video_id') THEN
        CREATE INDEX IF NOT EXISTS idx_posts_youtube_video ON posts(youtube_video_id);
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='user_id') AND 
       EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='status') THEN
        CREATE INDEX IF NOT EXISTS idx_posts_user_status ON posts(user_id, status);
    END IF;
    
    CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at);
    CREATE INDEX IF NOT EXISTS idx_posts_scheduled ON posts(status, scheduled_time);
    
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='campaign_id') THEN
        CREATE INDEX IF NOT EXISTS idx_posts_campaign ON posts(campaign_id) WHERE campaign_id IS NOT NULL;
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='tweet_id') THEN
        CREATE INDEX IF NOT EXISTS idx_posts_tweet_id ON posts(tweet_id) WHERE tweet_id IS NOT NULL;
    END IF;
END $$;

-- Clip jobs indexes
CREATE INDEX IF NOT EXISTS idx_clip_jobs_user ON clip_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_clip_jobs_status ON clip_jobs(status);
CREATE INDEX IF NOT EXISTS idx_clips_job ON clips(clip_job_id);

-- Comment jobs indexes
CREATE INDEX IF NOT EXISTS idx_comment_jobs_user_status ON comment_jobs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_comment_jobs_scheduled ON comment_jobs(scheduled_time) WHERE status = 'pending';

-- DM jobs indexes
CREATE INDEX IF NOT EXISTS idx_dm_jobs_user_status ON dm_jobs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_dm_jobs_scheduled ON dm_jobs(scheduled_time) WHERE status = 'pending';

-- DM conversations indexes
CREATE INDEX IF NOT EXISTS idx_dm_conversations_last_message ON dm_conversations(last_message_at);
CREATE INDEX IF NOT EXISTS idx_dm_messages_conversation ON dm_messages(conversation_id, created_at DESC);

-- Messages indexes
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversation_participants_user ON conversation_participants(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_unread ON messages(conversation_id, is_read) WHERE is_read = FALSE;

-- Twitter tokens indexes
CREATE INDEX IF NOT EXISTS idx_twitter_tokens_expires_at ON auth.twitter_tokens(expires_at) WHERE refresh_token IS NOT NULL;

-- Payment indexes
CREATE INDEX IF NOT EXISTS idx_post_payment_status ON auth.post_payment_intents(status);
CREATE INDEX IF NOT EXISTS idx_password_reset_token ON auth.password_reset_tokens(token);

-- PayPal indexes
CREATE INDEX IF NOT EXISTS idx_payment_intents_paypal_order ON auth.payment_intents(paypal_order_id) WHERE paypal_order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_post_payment_intents_paypal_order ON auth.post_payment_intents(paypal_order_id) WHERE paypal_order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_paypal_webhook_events_unprocessed ON auth.paypal_webhook_events(created_at) WHERE processed = FALSE;

-- =====================================================
-- STEP 7: FINAL VERIFICATION
-- =====================================================

-- Show all tables created
SELECT 
    table_schema,
    table_name,
    table_type
FROM information_schema.tables 
WHERE table_schema IN ('auth', 'app')
ORDER BY table_schema, table_name;

COMMIT;