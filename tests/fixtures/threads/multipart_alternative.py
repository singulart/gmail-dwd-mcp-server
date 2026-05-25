FIXTURE = {
    "description": "multipart/alternative plain + HTML",
    "payload": {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "bodyText": "Plain version",
            },
            {
                "mimeType": "text/html",
                "bodyText": "<p>HTML version</p>",
            },
        ],
    },
}
