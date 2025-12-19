import csv
import json
import argparse
import re
import html
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional


def normalize_header(h: str) -> str:
	return (h or "").strip().lower()


def map_columns(fieldnames: List[str]) -> Dict[str, str]:
	"""Map messy CSV headers to our expected keys."""
	mapping = {}
	for h in fieldnames:
		nh = normalize_header(h)
		# job URL should not be treated as title
		if "url" in nh:
			mapping["job_url"] = h
			continue
		# job description HTML should not be treated as a title either
		if "description" in nh and "html" in nh:
			# e.g. "Job_Description_HTML"
			mapping["job_description_html"] = h
			continue
		# prefer explicit "job title" column for job_title
		if nh in ("job title", "job_title", "title"):
			mapping["job_title"] = h
		elif any(k in nh for k in ("title", "position")):
			# only set if not already mapped by a more explicit header
			mapping.setdefault("job_title", h)
		elif "location" in nh or "city" in nh:
			mapping["location"] = h
		elif "date" in nh or "posted" in nh or "published" in nh:
			mapping["posted_date"] = h
		elif "salary" in nh or "pay" in nh or "compensation" in nh:
			mapping["salary"] = h
		elif any(k in nh for k in ("tech", "stack", "skills", "technologies")):
			mapping["tech_stack"] = h
	return mapping


def parse_tech_stack(s: Optional[str]) -> List[str]:
	if not s:
		return []
	# Try to focus on the part after "experience with", which usually lists skills
	m = re.search(r"experience with([^\.]+)", s, re.IGNORECASE)
	segment = m.group(1) if m else s
	parts = re.split(r"[,/]| and ", segment)
	skills: List[str] = []
	for p in parts:
		p = p.strip(" .;:!?\n\t")
		if not p:
			continue
		# remove leading helper phrases
		p = re.sub(r"^(experience with|you should have|should have)\s+", "", p, flags=re.IGNORECASE)
		if not p:
			continue
		skills.append(p)
	# de‑duplicate while preserving order
	seen = set()
	result: List[str] = []
	for sk in skills:
		key = sk.lower()
		if key in seen:
			continue
		seen.add(key)
		result.append(sk)
	return result


def extract_salary_phrase(s: str) -> str:
	"""Try to extract just the salary-related phrase from a longer text snippet."""
	text = s.strip()
	if not text:
		return ""
	# If it's already short, assume it's just the salary blob
	if len(text) <= 120:
		return text

	# Look for sentences/fragments mentioning salary-related words
	m = re.search(
		r"(salary[^\.!\n]*|compensation[^\.!\n]*|package[^\.!\n]*|rate[^\.!\n]*|pay[^\.!\n]*|wage[^\.!\n]*|remuneration[^\.!\n]*):?\s*[^\.!\n]+",
		text,
		re.IGNORECASE,
	)
	if m:
		return m.group(0).strip(" .")

	# Look for a money range or value with currency symbol or period indicator (more strict)
	m2 = re.search(
		r"[\$€£]\s?\d[\d,]*(?:\.\d+)?k?(?:\s*[-–]\s*[\$€£]?\s?\d[\d,]*(?:\.\d+)?k?)?(?:\s*(?:USD|GBP|EUR))?(?:\s*(?:per\s*(?:hour|day|week|month|year)|/hr|/hour|/day|/week|/month|/year|hr|hourly))?",
		text,
		re.IGNORECASE,
	)
	if m2:
		return m2.group(0).strip(" .")

	# Look for numbers with explicit period indicators (per hour/day/week/month/year)
	m3 = re.search(
		r"\d+[\d,]*(?:\.\d+)?k?\s*(?:per\s*(?:hour|day|week|month|year)|/hr|/hour|/day|/week|/month|/year|hr\b|hourly|daily|weekly|monthly|yearly)",
		text,
		re.IGNORECASE,
	)
	if m3:
		return m3.group(0).strip(" .")

	# Handle textual descriptors like "Competitive"
	m4 = re.search(r"\b(competitive|doe)\b", text, re.IGNORECASE)
	if m4:
		return m4.group(1)

	# Fallback: return empty string if we can't find clear salary indicators
	# This prevents extracting numbers from tech names
	return ""


def parse_salary(s: Optional[str]) -> Dict[str, Any]:
	"""Parse salary text into structured fields for display and filtering."""
	out: Dict[str, Any] = {
		"display": None,
		"min_amount": None,
		"max_amount": None,
		"currency_code": None,
		"currency_symbol": None,
		"period": None,
	}
	if not s:
		return out
	orig = s.strip()
	snippet = extract_salary_phrase(orig)
	
	# If extract_salary_phrase returns empty, no clear salary found - return all nulls
	if not snippet:
		return out
	
	text_lower = snippet.lower()

	# Check for clear salary indicators - require at least one of: currency, period, or salary keywords
	has_currency = bool(re.search(r"(\$|€|£|usd|gbp|eur)", snippet, re.IGNORECASE))
	has_period = bool(re.search(r"(per\s*(?:hour|day|week|month|year)|/hr|/hour|/day|/week|/month|/year|hr\b|hourly|daily|weekly|monthly|yearly|annum|annual|\byr\b|\bpa\b)", text_lower))
	has_salary_keywords = bool(re.search(r"\b(salary|compensation|package|rate|pay|wage|remuneration|base|bonus)\b", text_lower))

	if not (has_currency or has_period or has_salary_keywords):
		return out

	out["display"] = snippet

	# currency (normalized to 3-letter codes) + symbol
	cur_match = re.search(r"(\$|€|£|usd|gbp|eur)", snippet, re.IGNORECASE)
	if cur_match:
		cur_raw = cur_match.group(1).lower()
		if cur_raw in ("$", "usd"):
			out["currency_code"] = "USD"
			out["currency_symbol"] = "$"
		elif cur_raw in ("£", "gbp"):
			out["currency_code"] = "GBP"
			out["currency_symbol"] = "£"
		elif cur_raw in ("€", "eur"):
			out["currency_code"] = "EUR"
			out["currency_symbol"] = "€"

	# period (hour/day/week/month/year)
	period: Optional[str] = None
	if re.search(r"(per\s*hour|/hour|/hr|\shr\b|hourly)", text_lower):
		period = "hour"
	elif re.search(r"(per\s*day|/day|daily|day rate|daily rate)", text_lower):
		period = "day"
	elif re.search(r"(per\s*week|/week|weekly)", text_lower):
		period = "week"
	elif re.search(r"(per\s*month|/month|monthly|/mo\b)", text_lower):
		period = "month"
	elif re.search(r"(per\s*year|/year|annum|annual|yearly|\byr\b|\bpa\b|\bsalary\b|\bbase\b)", text_lower):
		period = "year"
	# Heuristic: ranges or single values in thousands, with no explicit shorter unit, are likely yearly
	if not period and re.search(r"\d+\s*k\b", text_lower):
		period = "year"
	out["period"] = period

	# normalize k suffix (e.g., 50k -> 50000)
	def _num_from_token(tok: str) -> Optional[float]:
		tok = tok.replace(',', '').strip()
		m = re.match(r"^(\d+(?:\.\d+)?)(k)?$", tok, re.IGNORECASE)
		if not m:
			return None
		val = float(m.group(1))
		if m.group(2):
			val *= 1000
		return val

	# find numeric tokens
	tokens = re.findall(r"\d+[\d,]*(?:\.\d+)?k?", snippet, re.IGNORECASE)
	nums = [_num_from_token(t) for t in tokens]
	nums = [n for n in nums if n is not None]
	if len(nums) == 1:
		out["min_amount"] = out["max_amount"] = int(nums[0])
	elif len(nums) >= 2:
		out["min_amount"] = int(min(nums))
		out["max_amount"] = int(max(nums))

	# Refine display to drop leading labels like "Daily rate:" or "Compensation:"
	if out["display"]:
		raw_txt = out["display"].strip()
		m_lead = re.search(r"[\$€£]|\d", raw_txt)
		if m_lead and m_lead.start() > 0:
			raw_txt = raw_txt[m_lead.start() :].lstrip()
		# If display becomes empty after refinement, set to None
		out["display"] = raw_txt if raw_txt else None

	# If we couldn't extract any structured info, clear display as well
	if (
		out["min_amount"] is None
		and out["max_amount"] is None
		and out["currency_code"] is None
		and out["period"] is None
	):
		out["display"] = None

	# Normalise period capitalisation (e.g. "year" -> "Year")
	if out["period"] is not None:
		out["period"] = str(out["period"]).capitalize()

	return out


def clean_html_description(s: Optional[str]) -> str:
	if not s:
		return ""
	# Strip HTML tags
	text = re.sub(r"<[^>]+>", " ", s)
	# Decode HTML entities
	text = html.unescape(text)
	# Replace standalone ampersands with a space
	text = text.replace("&", " ")
	# Normalise whitespace
	text = re.sub(r"\s+", " ", text)
	return text.strip()


def parse_posted_date(s: Optional[str]) -> Optional[str]:
	if not s:
		return None
	text = s.strip()
	if not text:
		return None

	# First try standard absolute date formats
	for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
		try:
			d = datetime.strptime(text, fmt).date()
			return d.isoformat()
		except ValueError:
			pass

	lower = text.lower()
	today = datetime.today().date()

	# Relative phrases
	if lower in ("today", "just now"):
		return today.isoformat()
	if lower == "yesterday":
		return (today - timedelta(days=1)).isoformat()

	m = re.match(r"^\s*(\d+)\s+day[s]?\s+ago\s*$", lower)
	if m:
		days = int(m.group(1))
		return (today - timedelta(days=days)).isoformat()

	m = re.match(r"^\s*(\d+)\s+week[s]?\s+ago\s*$", lower)
	if m:
		weeks = int(m.group(1))
		return (today - timedelta(days=7 * weeks)).isoformat()

	m = re.match(r"^\s*(\d+)\s+month[s]?\s+ago\s*$", lower)
	if m:
		months = int(m.group(1))
		# Approximate a month as 30 days
		return (today - timedelta(days=30 * months)).isoformat()

	m = re.match(r"^\s*(\d+)\s+year[s]?\s+ago\s*$", lower)
	if m:
		years = int(m.group(1))
		return (today - timedelta(days=365 * years)).isoformat()

	# Things like "3 hours ago", "45 minutes ago" -> treat as today
	if re.search(r"\bhour[s]?\s+ago\b", lower) or re.search(r"\bminute[s]?\s+ago\b", lower):
		return today.isoformat()

	# If nothing matches, treat as invalid and return None
	return None


def row_to_job(row: Dict[str, str], mapping: Dict[str, str]) -> Dict[str, Any]:
	job = {}
	job["job_title"] = row.get(mapping.get("job_title", ""), "").strip()
	location_raw = row.get(mapping.get("location", ""), "").strip()
	posted_raw = row.get(mapping.get("posted_date", ""), "").strip()
	job["job_url"] = row.get(mapping.get("job_url", ""), "").strip() or None
	# Normalise posted date into ISO YYYY-MM-DD if possible
	job["posted_date"] = parse_posted_date(posted_raw)
	desc_html = row.get(mapping.get("job_description_html", ""), "")
	job["job_description"] = clean_html_description(desc_html)

	# Normalise obviously invalid/placeholder locations to null
	if not location_raw or re.fullmatch(
		r"(?i)\s*(see\s+job\s+desc\.?|see\s+job\s+description\.?|n/?a|na)\s*", location_raw
	):
		location_value: Optional[str] = None
	else:
		location_value = location_raw

	job["location"] = location_value
	# Use explicit salary column if present and not just "Competitive", otherwise infer from description
	salary_raw = row.get(mapping.get("salary", ""), "").strip()
	if salary_raw and not re.search(r"\bcompetitive\b", salary_raw, re.IGNORECASE):
		salary_source = salary_raw
	else:
		salary_source = job["job_description"]
	job["salary"] = parse_salary(salary_source)
	# Prefer explicit tech/skills column if present, otherwise derive from description
	tech_raw = row.get(mapping.get("tech_stack", ""), "").strip()
	source_for_tech = tech_raw if tech_raw else job["job_description"]
	job["tech_stack"] = parse_tech_stack(source_for_tech)
	job["original_row"] = row
	return job


def convert_csv_to_json(inpath: str, outpath: str) -> None:
	with open(inpath, newline='', encoding='utf-8') as f:
		reader = csv.DictReader(f)
		fieldnames = reader.fieldnames or []
		mapping = map_columns(fieldnames)
		jobs = []
		seen_urls = set()
		for row in reader:
			job = row_to_job(row, mapping)
			job_url = (job.get("job_url") or "").strip().lower()
			if job_url:
				if job_url in seen_urls:
					# Skip duplicated entries by job_url
					continue
				seen_urls.add(job_url)
			jobs.append(job)

	with open(outpath, 'w', encoding='utf-8') as fo:
		json.dump(jobs, fo, ensure_ascii=False, indent=2)


def main():
	parser = argparse.ArgumentParser(description='Convert jobs CSV to structured JSON')
	parser.add_argument('input_csv', help='Path to input CSV file')
	parser.add_argument('output_json', nargs='?', default='jobs.json', help='Path to output JSON file (default: jobs.json)')
	args = parser.parse_args()
	convert_csv_to_json(args.input_csv, args.output_json)
	print(f'Wrote structured JSON to {args.output_json}')


if __name__ == '__main__':
	main()

