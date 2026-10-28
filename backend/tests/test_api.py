from io import BytesIO

def test_health(client):
    assert client.get("/api/health").status_code == 200

def test_register_login_and_reject_short_password(client):
    assert client.post("/api/auth/register", json={"email":"a@example.com", "password":"short"}).status_code == 400
    assert client.post("/api/auth/register", json={"email":"a@example.com", "password":"long-enough-password"}).status_code == 201
    assert client.post("/api/auth/login", json={"email":"a@example.com", "password":"wrong-password"}).status_code == 401
    assert client.post("/api/auth/login", json={"email":"a@example.com", "password":"long-enough-password"}).status_code == 200

def test_upload_list_and_share_download(client, auth_header):
    upload = client.post("/api/files", headers=auth_header, data={"file": (BytesIO(b"hello safe world"), "hello.txt")}, content_type="multipart/form-data")
    assert upload.status_code == 201
    file_id = upload.json["file"]["id"]
    assert len(client.get("/api/files", headers=auth_header).json["files"]) == 1
    share = client.post(f"/api/files/{file_id}/shares", headers=auth_header, json={"expires_in_hours": 1})
    assert share.status_code == 201
    token = share.json["url"].rsplit("/", 1)[-1]
    downloaded = client.get(f"/api/share/{token}")
    assert downloaded.status_code == 200
    assert downloaded.data == b"hello safe world"

def test_unsupported_extension_rejected(client, auth_header):
    response = client.post("/api/files", headers=auth_header, data={"file": (BytesIO(b"x"), "script.exe")}, content_type="multipart/form-data")
    assert response.status_code == 400

def test_user_cannot_access_another_users_file(client, auth_header):
    upload = client.post("/api/files", headers=auth_header, data={"file": (BytesIO(b"private"), "private.txt")}, content_type="multipart/form-data")
    file_id = upload.json["file"]["id"]
    client.post("/api/auth/register", json={"email":"other@example.com", "password":"another-long-password"})
    login = client.post("/api/auth/login", json={"email":"other@example.com", "password":"another-long-password"})
    other = {"Authorization": "Bearer " + login.json["access_token"]}
    assert client.delete(f"/api/files/{file_id}", headers=other).status_code == 404
