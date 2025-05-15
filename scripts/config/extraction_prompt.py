"""Contains the prompts for Gemini API extraction."""

EXTRACTION_PROMPT = """
Convert this Articulate Rise lesson PDF into clean, standalone markdown that preserves educational content while removing platform-specific elements.

## Core Principles
1. INCLUDE all educational content (text, concepts, explanations, activities, multi-media, questions)
2. EXCLUDE all platform-specific elements (navigation buttons, progress indicators, "lesson X of Y" labels)
3. REMOVE interface elements like [VIDEO BUTTON], [SUBMIT BUTTON], [DOWNLOAD ICON], etc.
4. CONVERT interactive elements to meaningful text-based alternatives

## 1. Add Section Markers
Add these HTML comment markers at the start of each corresponding section:
- `<!-- SECTION: INTRODUCTION -->`
- `<!-- SECTION: LEARNING-OBJECTIVES -->`
- `<!-- SECTION: TABLE-OF-CONTENTS -->`
- `<!-- SECTION: TERMS-AND-DEFINITIONS -->`
- `<!-- SECTION: MAIN-CONTENT-AREA -->` (for the core content)
- `<!-- SECTION: KEY-TAKEAWAYS -->`
- `<!-- SECTION: KNOWLEDGE-CHECK -->` (for activities and questions)
- `<!-- SECTION: REFERENCES -->`

## 2. Format Media Elements
For images:
![Description of the image](./[unit-title-id]-img-assets/fig[number]-[brief-description].png)
*Description: Details about the image*

For videos:
![VIDEO: Title of the video](https://example.com/video-url)
*Duration: [if available]*
*Description: Brief description of the video content*
*Source: [Channel Name](https://source-url)*

For webpages/external links:
![WEBPAGE: Title of the webpage](https://example.com/webpage-url)
*Description: Brief description of what can be found on this webpage*
*Source: [Website Name](https://example.com)*

## 3. Format Content Elements
### Regular Content
- Convert paragraphs, headings, lists as standard markdown
- Preserve emphasis (bold, italic) using markdown syntax
- Convert tables to proper markdown tables

### Interactive Elements
For accordions:
- **Accordion Title:** Content that was inside the accordion.

For tabs:
- **Tab Title:** Content that was inside the tab.

For process/timeline elements:
**Process: [Process Name]**
1. **Step 1:** Description of the first step.
2. **Step 2:** Description of the second step.

### Activities and Knowledge Checks
Convert to a clean format - remove all platform UI elements:
<!-- SECTION: KNOWLEDGE-CHECK -->
**Activity/Question [Number]:**
**Question:** [Question text]
**Options:**
- [Option text]
- [Option text]
- [Option text]
- [Option text]
**Answer:** [Answer text]
**Explanation:** [Explanation text]

## 5. Elements to Remove or Transform
REMOVE completely:
- Platform navigation elements ("Next", "Previous", etc.)
- Progress indicators ("Lesson 1 of 5", completion status)
- UI button text like [VIDEO BUTTON], [SUBMIT], [DOWNLOAD]
- Decorative elements that don't add educational value
- "Click here" instructions or similar platform-specific directives

TRANSFORM:
- Permissions blocks into simple source citations
- Information blocks (ℹ️) into regular text with appropriate emphasis
- Feedback sections into regular text answers/explanations

## Quality Checks
The final markdown should:
1. Be a self-contained educational document
2. Have no references to the original platform
3. Maintain all educational content and structure
4. Be readable as a standalone markdown document
5. Have all sections properly marked with HTML comments
6. Have appropriate placeholders for media elements

## Output Format
Please structure the output with the following metadata frontmatter at the top:

---
unit-id: {unit_id}
unit-title-id: {unit_title_id}
unit-title: [Extract the title from the document]
phase: {phase}
subject: [Extract the subject from the document]
parent-module-id: {parent_module_id}
parent-course-id: {parent_course_id}
batch-id: {batch_id}
extraction-date: {extraction_date}
extractor-name: "Automated Extraction"
---

Then follow with the properly formatted markdown content with all the appropriate section markers.
"""

def get_extraction_prompt(metadata):
    """Format the extraction prompt with metadata."""
    return EXTRACTION_PROMPT.format(**metadata)