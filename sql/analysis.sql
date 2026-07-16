-- SQLite-compatible portfolio queries.
-- Import data/processed/retail_store_sales_cleaned.csv as retail_sales.

-- 1. Monthly recorded sales and coverage by channel.
SELECT
    substr("Transaction Date", 1, 7) AS sales_month,
    "Location" AS channel,
    COUNT(*) AS total_records,
    COUNT("Total Spent") AS valid_sales_records,
    ROUND(SUM("Total Spent"), 2) AS recorded_sales,
    ROUND(AVG("Total Spent"), 2) AS sales_per_valid_transaction,
    ROUND(100.0 * COUNT("Total Spent") / COUNT(*), 2) AS sales_coverage_pct
FROM retail_sales
GROUP BY sales_month, channel
ORDER BY sales_month, channel;

-- 2. Top products by units, excluding low-sample products.
SELECT
    "Item" AS item,
    "Category" AS category,
    COUNT(*) AS transaction_count,
    SUM("Quantity") AS units_sold,
    ROUND(SUM("Total Spent"), 2) AS recorded_sales
FROM retail_sales
WHERE "Quantity" IS NOT NULL
  AND "Item Imputed" = 'No'
GROUP BY item, category
HAVING COUNT(*) >= 20
ORDER BY units_sold DESC
LIMIT 10;

-- 3. Missing-sales rate by category.
SELECT
    "Category" AS category,
    COUNT(*) AS total_records,
    SUM(CASE WHEN "Total Spent" IS NULL THEN 1 ELSE 0 END) AS missing_sales_records,
    ROUND(100.0 * SUM(CASE WHEN "Total Spent" IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2)
        AS missing_sales_pct
FROM retail_sales
GROUP BY category
ORDER BY missing_sales_pct DESC;

-- 4. Customer-level activity summary.
SELECT
    "Customer ID" AS customer_id,
    COUNT(*) AS transaction_count,
    COUNT("Total Spent") AS valid_sales_records,
    ROUND(SUM("Total Spent"), 2) AS recorded_sales,
    ROUND(AVG("Total Spent"), 2) AS average_transaction_value
FROM retail_sales
GROUP BY customer_id
ORDER BY recorded_sales DESC;

-- 5. Month-over-month recorded sales change.
WITH monthly AS (
    SELECT
        substr("Transaction Date", 1, 7) AS sales_month,
        SUM("Total Spent") AS recorded_sales
    FROM retail_sales
    GROUP BY sales_month
), compared AS (
    SELECT
        sales_month,
        recorded_sales,
        LAG(recorded_sales) OVER (ORDER BY sales_month) AS previous_month_sales
    FROM monthly
)
SELECT
    sales_month,
    ROUND(recorded_sales, 2) AS recorded_sales,
    ROUND(previous_month_sales, 2) AS previous_month_sales,
    ROUND(100.0 * (recorded_sales - previous_month_sales) / NULLIF(previous_month_sales, 0), 2)
        AS month_over_month_pct
FROM compared
ORDER BY sales_month;

