# Image Extraction Diagnostic Report
PDF: C:\Users\NevekLittlefordProje\Visual Studio Code Projects\microlearning_v2\original_content_pdf\CON0001_camb_as_physics\MOD0001_camb_as_physics_m1\UNI0001_camb_as_physics_m1_l1.pdf
Date: 2025-06-06 10:49:33
Total time: 0.07 seconds

## Summary
- Total identified images in PDF: 4
- Attempted extractions: 4
- Successfully extracted & processed: 0
- Failed extraction or processing/validation: 4
- Validation failures (extracted but invalid ImageIssueType): 4
- Total problematic images reported: 4

## Detailed Metrics
- Successful extractions (PIL image produced): 4
- Failed extractions (no PIL image produced): 0
- Retry successes (extracted after initial failure): 0
- Total extraction time (strategy attempts): 0.00 seconds

### Issue Type Breakdown (for problematic images)
- size_issues: 4

## Problematic Images Details
### Problematic Image 1 (Page 7, Index 0)
- **XREF**: 225
- **Issue**: File size too small: 685 bytes
- **Issue Type**: size_issues
- **Extraction Attempts**: 1
  - **Attempt History**:
    - Attempt 1: Strategy='standard', Status=SUCCESS, Duration=0.0030s
      - Dimensions: 298x154
      - Mode: RGB
- **Validation Details**: {'file_size': 685}

### Problematic Image 2 (Page 7, Index 1)
- **XREF**: 227
- **Issue**: File size too small: 642 bytes
- **Issue Type**: size_issues
- **Extraction Attempts**: 1
  - **Attempt History**:
    - Attempt 1: Strategy='standard', Status=SUCCESS, Duration=0.0000s
      - Dimensions: 298x154
      - Mode: RGB
- **Validation Details**: {'file_size': 642}

### Problematic Image 3 (Page 10, Index 0)
- **XREF**: 259
- **Issue**: File size too small: 145 bytes
- **Issue Type**: size_issues
- **Extraction Attempts**: 1
  - **Attempt History**:
    - Attempt 1: Strategy='standard', Status=SUCCESS, Duration=0.0000s
      - Dimensions: 149x149
      - Mode: RGB
- **Validation Details**: {'file_size': 145}

### Problematic Image 4 (Page 15, Index 0)
- **XREF**: 324
- **Issue**: File size too small: 145 bytes
- **Issue Type**: size_issues
- **Extraction Attempts**: 1
  - **Attempt History**:
    - Attempt 1: Strategy='standard', Status=SUCCESS, Duration=0.0000s
      - Dimensions: 150x149
      - Mode: RGB
- **Validation Details**: {'file_size': 145}

## Errors Log
- Processing/Validation failed for image on page 7, index 0: File size too small: 685 bytes
- Processing/Validation failed for image on page 7, index 1: File size too small: 642 bytes
- Processing/Validation failed for image on page 10, index 0: File size too small: 145 bytes
- Processing/Validation failed for image on page 15, index 0: File size too small: 145 bytes