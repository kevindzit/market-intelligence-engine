SELECT * FROM congressional_trades;
SELECT * FROM sec_filings;
SELECT * FROM company_profiles;



-- 2. Count the total number of trades saved
-- This is the best way to see if the scraper is adding new data.
SELECT COUNT(*) FROM congressional_trades;


-- 3. Find all trades made by a specific person
SELECT * FROM congressional_trades WHERE filer_name LIKE '%Boozman%';


-- 4. Find all trades for a specific stock ticker
-- Change 'ORCL' to 'AAPL', 'GOOG', etc.
SELECT * FROM congressional_trades WHERE ticker = 'ORCL';


-- 5. See a list of all unique people who have filed trades
SELECT DISTINCT filer_name FROM congressional_trades;


DELETE FROM congressional_trades
WHERE id BETWEEN 55 AND 63;



-- 6. Delete a single, specific trade by its ID
-- !! Always use a 'WHERE' clause when deleting, or you will delete everything.
-- find the 'id' of the row you want to delete, then run this.
-- DELETE FROM congressional_trades WHERE id = 1; -- (This is commented out for safety)


-- 7. Delete ALL data from the table (for a fresh start)
-- !! DANGER: This will wipe your table clean. There is no undo.
-- TRUNCATE TABLE congressional_trades; -- (This is commented out for safety



SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'congressional_trades';



SELECT * FROM economic_indicators;

SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';



-- check twitter dbu overall

SELECT token, COUNT(*), AVG(sentiment_score) 
FROM twitter_sentiment 
GROUP BY token;



-- Track Sentiment Trends

Query to see if sentiment is improving or getting worse:
SELECT 
    DATE_TRUNC('hour', scraped_at) as hour,
    token,
    AVG(sentiment_score) as avg_sentiment
FROM twitter_sentiment
WHERE scraped_at > NOW() - INTERVAL '24 hours'
GROUP BY hour, token
ORDER BY hour DESC;



-- Find Most Influential Tweets

SELECT token, tweet_text, sentiment_score,
       (retweet_count + like_count) as engagement
FROM twitter_sentiment
WHERE sentiment_score > 0.5
ORDER BY engagement DESC
LIMIT 20;



