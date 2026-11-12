# Job Scraper – HTML Diff Pipeline

## Main idea

Python compares the previous and current cleaned HTML. It does not need to know each website's CSS classes or which HTML element is a job card. AI receives changed content and decides whether it represents a new, updated or removed vacancy, or an irrelevant website change.

## Run

1. Install the project's Python dependencies in your virtual environment.
2. Create a local .env file with WP_USERNAME, WP_APPLICATION_PASSWORD, META_API_KEY and optionally META_MODEL.
3. Check sites.json.
4. Run: python main.py

The first run for each employer sends its complete cleaned HTML to AI once. This establishes the initial WordPress job list and HTML snapshot. Later runs send only differences.

## File structure

| File | Responsibility |
|---|---|
| main.py | Orchestrates all stages; entry point |
| scraping.py | Downloads pages with Crawl4AI and cleans generic HTML |
| html_diff.py | Compares old and new HTML; separates additions and removals |
| sending_to_ai.py | Sends both change directions in one request; validates AI response |
| wordpress.py | Reads, creates, updates and drafts WordPress jobs |
| state.py | Saves HTML baseline and pending removals |
| utils.py | URL normalization and URL presence checks |
| sites.json | Employer website configuration |
| scrape_output/ | Local snapshots and state; must persist between runs |

The previous pipeline.py and scrape.py are retained on this feature branch for reference. The new entry point is main.py.

## One website run – what happens and when?

### 1. SCRAPING – scraping.py

Crawl4AI downloads the careers page. The cleaner removes scripts, styles, media, HTML comments and unstable attributes. It keeps HTML containers, text and links. Links can identify a specific vacancy.

No site-specific CSS selectors are used. The same cleaner is used for every configured website.

### 2. HTML DIFF – html_diff.py

Python compares current cleaned HTML with the last successfully processed snapshot.

- Same HTML: no AI request.
- Changed HTML: compute a unified textual diff.
- added_content: lines present in the new page but not in the old page.
- removed_content: lines present in the old page but not in the new page.
- diff_text: unified diff including surrounding context.

Both additions and removals are sent together. This covers a page update where one vacancy disappears and another appears at the same time.

Important: this is a textual diff, not a semantic HTML diff. A layout rewrite or reordered HTML can produce a large diff. AI interprets the meaning of the changes.

### 3. SENDING TO AI – sending_to_ai.py

One request contains:
- Careers page URL and employer name.
- Employer slug for context.
- Configured default address and canton.
- Added HTML.
- Removed HTML.
- Unified diff context.

AI returns four arrays:

| AI output | Meaning |
|---|---|
| new_jobs | Vacancies identified in added content |
| updated_jobs | Existing vacancies whose details changed |
| removed_jobs | Removal candidates identified in removed content |
| irrelevant_changes | Cookie, navigation, footer or other unrelated changes |

AI handles semantic classification. Python does not decide whether a changed block is a job vacancy.

The response is validated. Every returned job needs a title and valid HTTP(S) URL before WordPress operations begin.

### 4. WORDPRESS UPSERT – wordpress.py

Current WordPress matching uses:
- ACF source_url to scope posts to the configured careers page.
- ACF job_url as the primary identity of a vacancy.
- URL normalization to ignore common tracking parameters, www differences and trailing slashes.

If the normalized URL already exists, update that post. If it does not exist, create a post.

The slug in sites.json is currently used for local filenames and logs. It is not written to WordPress because an employer_slug ACF field has not been confirmed as created and exposed through REST. Existing source_url is used as the employer scope.

### 5. REMOVAL CHECK – main.py and wordpress.py

AI removal results are candidates only. They are not immediately drafted.

- First successful scan where AI identifies a removal: save it as pending with missing_scans = 1.
- Next successful scan: check whether its job URL is still present in the current page.
- If the URL has returned: cancel the pending removal.
- If the URL is still absent: increment the counter and set the matching published WordPress post to Draft at count 2.

The second confirmation happens before newly detected removals are queued. This ensures a new removal starts at 1/2, not 2/2 in the same run.

A failed scrape, AI request or WordPress operation prevents the HTML snapshot from advancing. The next run can retry the same diff.

### 6. SAVE SNAPSHOT – state.py

Only after processing completes, save the new cleaned HTML and state JSON. The state file stores pending removals and the last successful scan timestamp.

Example files for stoos-hotels:
- scrape_output/stoos-hotels.html
- scrape_output/stoos-hotels_state.json

The scrape_output folder is local runtime state and should not be committed. If using another computer or GitHub Actions, persist this folder between runs or every run behaves like a first run.

## Limitations

1. HTML diff is textual. A redesign can produce a large diff and higher AI token usage.
2. AI can still miss a vacancy in a changed section. Schema validation cannot guarantee completeness.
3. Removal is conservative: AI must identify it, and the URL must remain absent across two successful scans.
4. If a job URL changes, current WordPress matching cannot safely infer identity from title alone. URL is the primary identity. A stable external job ID or reviewed title matching can be added later.
5. First run is more expensive because it sends the complete cleaned page once.

## Suggested validation

1. Back up current WordPress jobs.
2. Test one employer and inspect the first AI result.
3. Run again without page changes; AI should be skipped.
4. Test a page update with one addition and one removal.
5. Check that the new job is created and the old job becomes Draft only after the second successful scan.
6. Inspect token counts and diff output.

The code has not been tested against the live Meta AI service or WordPress API in this editing session. Validate against a test employer before production use.
