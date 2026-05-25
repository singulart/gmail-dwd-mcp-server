FIXTURE = {
    "description": "multipart/mixed with alternative + PDF attachment",
    "payload": {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "bodyText": "Nested plain body",
                    },
                    {
                        "mimeType": "text/html",
                        "bodyText": "<p>Nested HTML</p>",
                    },
                ],
            },
            {
                "mimeType": "application/pdf",
                "filename": "report.pdf",
                "body": {
                    "attachmentId": "ANGjdJ_example",
                    "size": 1024,
                },
            },
        ],
    },
}
