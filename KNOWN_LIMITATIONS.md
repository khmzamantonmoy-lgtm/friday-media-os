# Known Limitations & System Constraints
**Target Project:** `friday-media-os`  
**Status:** Documented  

This document lists the operational boundaries, performance costs, and potential failures that system maintainers should monitor.

---

## 1. RENDERING PERFORMANCE OVERHEAD
*   **Outro Rendering Cost:** Dynamically compositing the outro using MoviePy (`ColorClip`, `TextClip`, and layouts) adds an extra `5-10 seconds` of rendering overhead per video.
*   **Resolution:** Outro generation uses standard fonts and flat colors to keep rendering fast. If performance bottlenecks occur, the outro could be pre-rendered as a static video file and simply concatenated using FFmpeg directly (bypassing MoviePy frame composition).

---

## 2. IMAGEMAGICK SECURITY POLICY
*   **Issue:** Many default Linux packages install ImageMagick with highly restrictive policies in `/etc/ImageMagick-6/policy.xml` that disable PDF/Text conversions, causing MoviePy `TextClip` rendering failures.
*   **Mitigation:** The active Cloud Shell VM and the pipeline container Dockerfile contain scripts to explicitly permit text and read-write actions. Maintenance scripts must ensure these permissions remain enabled during image updates.

---

## 3. VERTEX AI / GEMINI API QUOTAS
*   **Issue:** Concurrent pipelines running in parallel may exceed the Rate Limits (Requests Per Minute - RPM, or Tokens Per Minute - TPM) on the `gemini-2.5-flash` model.
*   **Mitigation:** If massive batch operations are triggered, the pipeline coordinator must implement exponential backoff retry algorithms to handle `429 ResourceExhausted` errors gracefully.

---

## 4. AUDIO AND OUTRO TIMING LIMITS
*   **Issue:** The main video audio track (narration) cuts off at the start of the outro. The outro plays in silence (unless background music is added).
*   **Mitigation:** This is the designed behavior to focus the user's attention on the visual CTAs. If background music is introduced in a future sprint, the music audio clip should be configured to cover both the main duration and the outro duration, fading out in the final 1-2 seconds.
