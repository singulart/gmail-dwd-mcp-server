_HEADERS = [
    {"name": "Subject", "value": "Long thread subject"},
    {"name": "From", "value": "sender@example.com"},
]

FIXTURE = {
    "description": "Thread with 12 messages for limit and window tests",
    "id": "thread-long-001",
    "messages": [
        {
            "id": f"msg-{index:02d}",
            "snippet": f"Thread message {index}",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    *_HEADERS,
                    {"name": "Date", "value": f"Mon, {index} Jan 2024 10:00:00 +0000"},
                ],
                "bodyText": f"Thread message {index}",
            },
        }
        for index in range(1, 13)
    ],
}
