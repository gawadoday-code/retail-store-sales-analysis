# Data dictionary

| Field | Type | Definition | Quality note |
|---|---|---|---|
| Transaction ID | Text | Unique record identifier | Complete and unique in the cleaned data |
| Customer ID | Text | Customer identifier | Only 25 identifiers; privacy status requires confirmation |
| Category | Category | Product category | Eight categories |
| Item | Category | Product identifier | 1,213 values were internally inferred; see `Item Imputed` |
| Price Per Unit | Numeric | Recorded unit price | 609 values were derived from total divided by quantity |
| Quantity | Numeric | Units recorded on the transaction | Missing in 604 rows |
| Total Spent | Numeric | Recorded transaction amount | Missing in 604 rows; gross/net meaning is unconfirmed |
| Payment Method | Category | Cash, Credit Card, or Digital Wallet | Complete |
| Location | Category | Online or In-store | Interpreted as channel; confirm source definition |
| Transaction Date | Date | Transaction calendar date | Range: 2022-01-01 to 2025-01-18 |
| Discount Applied | Category | Yes, No, or Unknown | Unknown in 4,199 rows; discount amount is unavailable |
| Year | Integer | Calendar year derived from date | Derived field |
| Month | Integer | Calendar month number | Derived field |
| Month Name | Text | Calendar month name | Derived field |
| Quarter | Category | Calendar quarter | Derived field |
| Weekday | Category | Day name | Derived field |
| Item Imputed | Boolean text | Whether item was internally inferred | Never use target-derived inference as a predictive feature |
| Price Imputed | Boolean text | Whether price was derived from total and quantity | Descriptive recovery only; target-derived |
| Arithmetic Issue | Boolean text | Price × quantity differs from total | No issues in complete records |
| Total Outlier IQR | Boolean text | Total falls outside the 1.5×IQR bounds | High-value flag, not an error label |
| Missing Pattern | Text | Human-readable unresolved/unknown fields | Audit field |

