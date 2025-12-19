## Job CSV → JSON Converter

This script converts a messy jobs CSV (like `messy_jobs.csv`) into a cleaned, structured JSON file (for example `output.json`) with normalized fields such as `job_title`, `job_description`, and `salary`.

### Requirements

- **Python**: 3.8 or higher
- **Dependencies**: only the Python standard library (no extra `pip` installs needed)
- **Optional**: a virtual environment to isolate Python packages

### Project Structure

- `main.py` – CLI script that reads the CSV and writes the structured JSON.
- `messy_jobs.csv` – example input CSV with raw job data.
- `output.json` – example output JSON (can be overwritten by running the script).

### Setup

1. **Open the project directory**

   ```bash
   cd path/to/job-parser
   ```

2. **(Optional) Create and activate a virtual environment**

   ```bash
   python -m venv venv
   ```

   - **Windows (PowerShell)**:

     ```bash
     .\venv\Scripts\Activate.ps1
     ```

   - **Windows (cmd)**:

     ```bash
     .\venv\Scripts\activate.bat
     ```

   No additional packages are required; you can run the script with the standard library only.

### How to Run

From the project root (same folder as `main.py`):

```bash
python main.py input_csv [output_json]
```

- **`input_csv`** (required): path to the input CSV file
  - Example: `messy_jobs.csv`
- **`output_json`** (optional): path to the output JSON file
  - If omitted, the default is `jobs.json`

#### Examples

```bash
# Using the provided CSV and default output name
python main.py messy_jobs.csv

# Using the provided CSV and a custom output file name
python main.py messy_jobs.csv output.json
```

After running, open the JSON file (e.g. `output.json`) to inspect the transformed job data.

### Output JSON Structure (per job)

Each job in the output JSON is an object with fields similar to:

```json
{
  "job_title": "Lead Dynamics CRM",
  "job_url": "https://example.com/job/123",
  "location": "Berlin",
  "posted_date": "2025-12-10",
  "job_description": "We are looking for a skilled professional to join our team. You should have experience with SQL, Business Central. Role involves building solutions on the Microsoft Stack. Daily rate: $500 - $650.",
  "tech_stack": ["SQL", "Business Central"],
  "salary": {
    "display": "$500 - $650",
    "min_amount": 500,
    "max_amount": 650,
    "currency_code": "USD",
    "currency_symbol": "$",
    "period": "Day"
  },
  "original_row": {
    "...": "..."
  }
}
```

#### Field Notes

- **`job_title`**: taken from the `Job Title` (or similar) column in the CSV.
- **`job_url`**: taken from any URL-like column; used to **de‑duplicate** rows. If multiple rows share the same `job_url`, only the first is kept in the output.
- **`location`**:
  - Normalised string from the CSV location column.
  - Placeholder values such as `"See Job Desc."`, `"See Job Description"`, `"N/A"`, `"NA"` (case-insensitive) are converted to `null` in the JSON.
- **`posted_date`**:
  - Normalised to ISO `YYYY-MM-DD` where possible.
  - Supports absolute formats like `2025-12-10`, `12/10/2025`, `10/12/2025`.
  - Relative strings such as `"today"`, `"yesterday"`, `"2 days ago"`, `"3 weeks ago"`, `"2 months ago"`, `"1 year ago"`, `"3 hours ago"` are converted to a concrete date based on the day the script is run.
  - If the date cannot be parsed, this field is set to `null`.
- **`job_description`**: plain-text description with HTML tags removed and HTML entities cleaned.
- **`tech_stack`**: list of skills/technologies parsed from a dedicated tech/skills column when available, otherwise from the description text.
- **`salary`**:
  - **`display`**: short salary text only (for example `"$500 - $650"`), or `null` when nothing useful can be extracted.
  - **`min_amount` / `max_amount`**: numeric min/max values if they can be parsed; otherwise `null`.
  - **`currency_code`**: normalised 3-letter code (`USD`, `GBP`, `EUR`) or `null`.
  - **`currency_symbol`**: corresponding symbol (`$`, `£`, `€`) or `null`.
  - **`period`**: capitalised unit like `Hour`, `Day`, `Week`, `Month`, `Year`, or `null`.
- **`original_row`**: the full original CSV row for debugging or additional fields you might need later.
