import http.client, uuid, time, json, hmac, hashlib

SECRET ="dev-shared-secret"

def send_test_events(base_url="http://localhost:8000",n=5,event_type="test_event"):
    for i in range(n):
        event_id = str(uuid.uuid4().hex)
        payload = {
            "event_id": event_id,
            "event_type": event_type,
            "data": {"message": f"Test event {i}"},
            "ts": int(time.time())
        }

        payload_bytes = json.dumps(payload).encode()

        signature = hmac.new(SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()
        print(f"Generated signature for event {event_id}: {signature}")
        headers = {"X-Signature": f"sha256={signature}"}
        
        conn = http.client.HTTPConnection("localhost", 8000)
        conn.request("POST", "/webhook", body=payload_bytes, headers=headers)
        response = conn.getresponse()
        print(f"Sent event {event_id}, status: {response.status}")
        conn.close()

if __name__ == "__main__":
    send_test_events()