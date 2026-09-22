# TODO

## Azure AI Search File Knowledge Source Upload

-   Investigate why uploading travel review files to the Azure AI Search file
    knowledge source fails during processing. The scripted REST upload currently
    reaches the service, but the service returns `File upload processing failed`.
-   Investigate why adding the same data through the Azure portal / Foundry UI is
    also failing. Because both scripted upload and UI upload fail, treat this as
    a Search service / knowledge-source configuration or preview feature issue,
    not only a local script formatting issue.
-   Capture the failing request IDs from Azure AI Search and use them when
    checking Azure diagnostics or opening a support issue.
-   Confirm the exact supported upload format for `2026-08-01-preview` in the
    current region and service tier. We have tried markdown, plain text, JSON,
    raw `application/octet-stream`, base64 JSON string, and multipart upload.
-   Re-check whether the Search service managed identity has access to the
    embedding deployment and whether the embedding deployment endpoint/model name
    match the knowledge-source payload.
-   If file knowledge-source upload remains blocked, evaluate a fallback path:
    create a conventional Azure AI Search index and upload parsed review records
    with `SearchClient.upload_documents`, then expose that index through the
    toolbox `azure_ai_search` tool.