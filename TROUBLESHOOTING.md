# FRIDAY Media OS — Troubleshooting

## Worker Failures
### Render Worker (FFmpeg)
*   **Error**: `MoviePy Error: [Errno 32] Broken pipe`.
*   **Cause**: Usually an incompatible frame size or corrupted image.
*   **Solution**: Verify the `Image Worker` output in GCS. Ensure all frames are vertical 1080x1920.

### Image Worker (Gemini 2.5 Image)
*   **Error**: `No image returned`.
*   **Cause**: Safety filters triggered by the prompt.
*   **Solution**: Adjust the `visual_style` in `brand_registry.py` to be more neutral.

## Dashboard Issues
### Firestore Connection
*   **Error**: `PermissionDenied: project cloudshell-gca`.
*   **Cause**: Incorrect environmental project binding.
*   **Solution**: Ensure `firestore.Client(project="friday-media-prod")` is used.

### UI Mismatch
*   **Error**: "The deployed revision runs an older image".
*   **Cause**: `deploy.sh` succeeded but the revision failed to roll out.
*   **Solution**: Run `gcloud run services describe media-ui` to check deployment status.
