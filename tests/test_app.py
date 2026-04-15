from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import ANY, patch

from pypdf import PdfWriter

from src.paper_reader.app import create_app, load_env_file_values
from src.paper_reader.markdown_render import render_markdown


DOCX_CONTENT_TYPES = """<?xml version='1.0' encoding='UTF-8'?>
<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>
  <Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>
  <Default Extension='xml' ContentType='application/xml'/>
  <Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/>
  <Override PartName='/docProps/core.xml' ContentType='application/vnd.openxmlformats-package.core-properties+xml'/>
</Types>
"""

DOCX_RELS = """<?xml version='1.0' encoding='UTF-8'?>
<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>
  <Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/>
  <Relationship Id='rId2' Type='http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties' Target='docProps/core.xml'/>
</Relationships>
"""

DOCX_DOC = """<?xml version='1.0' encoding='UTF-8'?>
<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>
  <w:body>
    <w:p><w:r><w:t>{title}</w:t></w:r></w:p>
    <w:p><w:r><w:t>{body}</w:t></w:r></w:p>
  </w:body>
</w:document>
"""

DOCX_CORE = """<?xml version='1.0' encoding='UTF-8'?>
<cp:coreProperties xmlns:cp='http://schemas.openxmlformats.org/package/2006/metadata/core-properties'
 xmlns:dc='http://purl.org/dc/elements/1.1/'>
  <dc:title>{title}</dc:title>
</cp:coreProperties>
"""


class PaperReaderAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.library = Path(self.tempdir.name)
        self.source_tempdir = tempfile.TemporaryDirectory()
        self.env_file_path = self.library / ".test-no-env"
        self.env_patch = patch.dict(os.environ, {"PAPER_READER_ENV_FILE": str(self.env_file_path)}, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.source_root = Path(self.source_tempdir.name)
        self.app = create_app(self.library, source_archive_root=self.source_root)
        self.app.testing = True
        self.client = self.app.test_client()
        admin_user = self.app.team_store.get_user_by_username("admin")
        assert admin_user is not None
        with self.client.session_transaction() as session:
            session["authenticated"] = True
            session["user_id"] = admin_user.id
            session["username"] = admin_user.username
            session["display_name"] = admin_user.display_name
            session["role"] = admin_user.role

    def tearDown(self) -> None:
        try:
            self.app.job_queue.stop_all()
            for _ in range(50):
                snapshot = self.app.job_queue.snapshot(limit=5)
                if snapshot["active_count"] == 0:
                    break
                time.sleep(0.01)
        except Exception:
            pass
        self.source_tempdir.cleanup()
        self.tempdir.cleanup()

    def make_pdf(self, path: Path, title: str) -> None:
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.add_metadata({"/Title": title})
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            writer.write(handle)

    def make_docx(self, path: Path, title: str, body: str) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", DOCX_CONTENT_TYPES)
            archive.writestr("_rels/.rels", DOCX_RELS)
            archive.writestr("word/document.xml", DOCX_DOC.format(title=title, body=body))
            archive.writestr("docProps/core.xml", DOCX_CORE.format(title=title))

    def login_client_as(self, client, username: str) -> None:
        user = self.app.team_store.get_user_by_username(username)
        assert user is not None
        with client.session_transaction() as session:
            session["authenticated"] = True
            session["user_id"] = user.id
            session["username"] = user.username
            session["display_name"] = user.display_name
            session["role"] = user.role

    def create_prompt(self, slug: str, name: str) -> None:
        admin_user = self.app.team_store.get_user_by_username("admin")
        assert admin_user is not None
        self.app.prompt_store.save_prompt(
            existing_slug=None,
            name=name,
            slug=slug,
            user_prompt="请直接阅读 `{document_path}`，总结这篇论文。",
            model="gpt-5.4",
            enabled=True,
            auto_run=False,
            created_by_user_id=admin_user.id,
        )

    def create_source_day(self, run_date: str, paper_id: str = "2604.08377", title: str = "SkillClaw") -> Path:
        year, month, day = run_date.split("-")
        day_dir = self.source_root / year / month / day
        pdf_dir = day_dir / "papers"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"{paper_id}.pdf"
        self.make_pdf(pdf_path, title)
        manifest = {
            "run_reason": "startup",
            "run_date_beijing": run_date,
            "saved_at_beijing": f"{run_date}T18:30:00+08:00",
            "saved_at_utc": f"{run_date}T10:30:00+00:00",
            "schedule_timezone": "Asia/Shanghai",
            "schedule_time_beijing": "18:30",
            "source": "huggingface_daily_papers",
            "source_url": "https://huggingface.co/papers",
            "snapshot_date": run_date,
            "filter": {"field": "upvotes", "operator": ">=", "value": 5},
            "paper_count": 1,
            "papers": [
                {
                    "paper_id": paper_id,
                    "title": title,
                    "url": f"https://huggingface.co/papers/{paper_id}",
                    "upvotes": 12,
                    "published_at": f"{run_date}T00:00:00.000Z",
                    "authors": ["Alice", "Bob"],
                    "summary": "A source archive test paper.",
                    "comment_count": 2,
                    "pdf_url": f"https://arxiv.org/pdf/{paper_id}.pdf",
                    "pdf_rel_path": f"papers/{paper_id}.pdf",
                    "pdf_file_name": f"{paper_id}.pdf",
                    "pdf_downloaded": True,
                }
            ],
        }
        (day_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return pdf_path

    def test_login_required_for_index(self) -> None:
        client = self.app.test_client()
        response = client.get("/", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_login_allows_access_with_correct_credentials(self) -> None:
        client = self.app.test_client()
        response = client.post(
            "/login",
            data={
                "username": "admin",
                "password": "paperpaperreaderreader12678",
                "next": "/",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_login_locks_for_five_minutes_after_three_failures(self) -> None:
        client = self.app.test_client()
        guard = self.app.login_guard
        original_now = guard._now
        timeline = {"value": 1000.0}
        guard._now = lambda: timeline["value"]
        self.addCleanup(setattr, guard, "_now", original_now)

        for _ in range(3):
            response = client.post(
                "/login",
                data={"username": "admin", "password": "wrong", "next": "/"},
                follow_redirects=True,
            )

        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("已锁定 5 分钟", html)

        blocked = client.post(
            "/login",
            data={"username": "admin", "password": "paperpaperreaderreader12678", "next": "/"},
            follow_redirects=True,
        )
        self.assertIn("当前已锁定", blocked.get_data(as_text=True))

        timeline["value"] += 301
        success = client.post(
            "/login",
            data={"username": "admin", "password": "paperpaperreaderreader12678", "next": "/"},
            follow_redirects=False,
        )
        self.assertEqual(success.status_code, 302)
        self.assertEqual(success.headers["Location"], "/")

    def test_login_credentials_can_be_overridden_by_env_file(self) -> None:
        env_file = self.library / ".env.custom"
        env_file.write_text(
            "PAPER_READER_LOGIN_USERNAME=reader\nPAPER_READER_LOGIN_PASSWORD=custom-secret-456\n",
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"PAPER_READER_ENV_FILE": str(env_file)}, clear=False):
            app = create_app(self.library)
        app.testing = True
        client = app.test_client()

        custom_login = client.post(
            "/login",
            data={"username": "reader", "password": "custom-secret-456", "next": "/"},
            follow_redirects=False,
        )
        self.assertEqual(custom_login.status_code, 302)
        self.assertEqual(custom_login.headers["Location"], "/")

    def test_load_env_file_values_parses_simple_dotenv(self) -> None:
        env_file = self.library / ".env.parse"
        env_file.write_text(
            "# comment\nexport PAPER_READER_LOGIN_USERNAME='reader'\nPAPER_READER_LOGIN_PASSWORD=\"secret\"\n",
            encoding="utf-8",
        )

        values = load_env_file_values(env_file)

        self.assertEqual(values["PAPER_READER_LOGIN_USERNAME"], "reader")
        self.assertEqual(values["PAPER_READER_LOGIN_PASSWORD"], "secret")

    def test_admin_can_create_member_user(self) -> None:
        response = self.client.post(
            "/team/users/save",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "paper": "",
                "tab": "source",
                "username": "alice",
                "display_name": "Alice",
                "password": "alice-pass-123",
                "role": "member",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        created_user = self.app.team_store.get_user_by_username("alice")
        self.assertIsNotNone(created_user)
        self.assertEqual(created_user.role, "member")

        login_client = self.app.test_client()
        login = login_client.post(
            "/login",
            data={"username": "alice", "password": "alice-pass-123", "next": "/"},
            follow_redirects=False,
        )
        self.assertEqual(login.status_code, 302)
        self.assertEqual(login.headers["Location"], "/")

    def test_admin_can_update_member_password_role_and_status(self) -> None:
        self.app.team_store.create_user("alice", "Alice", "alice-pass-123", "member")
        alice = self.app.team_store.get_user_by_username("alice")
        assert alice is not None

        response = self.client.post(
            "/team/users/update",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "paper": "",
                "tab": "source",
                "user_id": str(alice.id),
                "display_name": "Alice Chen",
                "role": "admin",
                "is_active": "on",
                "new_password": "new-pass-456",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        updated = self.app.team_store.get_user_by_username("alice")
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated.display_name, "Alice Chen")
        self.assertEqual(updated.role, "admin")
        self.assertIsNone(self.app.team_store.authenticate_user("alice", "alice-pass-123"))
        self.assertIsNotNone(self.app.team_store.authenticate_user("alice", "new-pass-456"))

        deactivate = self.client.post(
            "/team/users/update",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "paper": "",
                "tab": "source",
                "user_id": str(alice.id),
                "display_name": "Alice Chen",
                "role": "admin",
            },
            follow_redirects=True,
        )

        self.assertEqual(deactivate.status_code, 200)
        deactivated = self.app.team_store.get_user_by_username("alice")
        self.assertIsNotNone(deactivated)
        assert deactivated is not None
        self.assertFalse(deactivated.is_active)
        self.assertIsNone(self.app.team_store.authenticate_user("alice", "new-pass-456"))

    def test_member_cannot_edit_prompts(self) -> None:
        self.app.team_store.create_user("alice", "Alice", "alice-pass-123", "member")
        client = self.app.test_client()
        self.login_client_as(client, "alice")

        response = client.post(
            "/prompt-save",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "paper": "",
                "tab": "source",
                "name": "方法拆解",
                "slug": "method-breakdown",
                "user_prompt": "请解释方法。",
                "model": "gpt-5.4",
                "enabled": "on",
                "auto_run": "on",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("只有管理员能处理", response.get_data(as_text=True))
        self.assertIsNone(self.app.prompt_store.get_prompt("method-breakdown"))

    def test_member_upload_uses_managed_inbox_and_cannot_rename_files(self) -> None:
        self.app.team_store.create_user("alice", "Alice", "alice-pass-123", "member")
        client = self.app.test_client()
        self.login_client_as(client, "alice")

        upload_bytes = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(upload_bytes)
        upload_bytes.seek(0)

        with patch.object(
            self.app.job_queue,
            "submit",
            return_value={"queued": 1, "existing": 0, "skipped": 0, "invalid": 0, "job_ids": [], "jobs": []},
        ) as mocked:
            response = client.post(
                "/upload-file",
                data={
                    "target_folder": "secret/admin-only",
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "file": (upload_bytes, "single.pdf"),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["saved_rel_path"], "TeamInbox/alice/single.pdf")
        mocked.assert_called_once_with(
            ["TeamInbox/alice/single.pdf"],
            ["core-zh"],
            force=False,
            source="upload",
            requested_by_user_id=ANY,
            requested_by_display_name="Alice",
        )

        rename_response = client.post(
            "/rename",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "show_done": "",
                "tab": "source",
                "rel_path": "TeamInbox/alice/single.pdf",
                "new_name": "renamed.pdf",
            },
            follow_redirects=True,
        )
        html = rename_response.get_data(as_text=True)

        self.assertEqual(rename_response.status_code, 200)
        self.assertIn("只有管理员能处理", html)
        self.assertTrue((self.library / "TeamInbox" / "alice" / "single.pdf").exists())
        self.assertFalse((self.library / "TeamInbox" / "alice" / "renamed.pdf").exists())

    def test_team_metadata_is_visible_and_searchable(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Robot Policy")
        response = self.client.post(
            "/recommend",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "show_done": "",
                "rel_path": "paper.pdf",
                "tab": "source",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/tags/add",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "show_done": "",
                "rel_path": "paper.pdf",
                "tab": "source",
                "tag_name": "robotics",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/like-toggle",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "show_done": "",
                "rel_path": "paper.pdf",
                "tab": "source",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/comments",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "show_done": "",
                "rel_path": "paper.pdf",
                "tab": "source",
                "body": "这个结果很适合组会分享。",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("1 人推荐", html)
        self.assertIn("#robotics", html)
        self.assertIn("1 条评论", html)
        self.assertIn("1 个赞", html)

        search_response = self.client.get("/?q=robotics")
        self.assertIn("Robot Policy", search_response.get_data(as_text=True))

    def test_shared_and_private_chat_threads_are_persisted_separately(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Chat Paper")
        self.app.team_store.create_user("alice", "Alice", "alice-pass-123", "member")
        alice_client = self.app.test_client()
        self.login_client_as(alice_client, "alice")

        replies = iter(["团队共享回答", "私人回答"])

        def complete_chat(**kwargs):
            self.app.team_store.update_chat_message(
                kwargs["assistant_message_id"],
                body=next(replies),
                status="completed",
                model="gpt-5.4",
            )

        with patch.object(self.app.chat_queue, "submit", side_effect=complete_chat):
            shared_response = self.client.post(
                "/chat/send",
                data={
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "show_done": "",
                    "rel_path": "paper.pdf",
                    "tab": "source",
                    "visibility": "shared",
                    "body": "这篇论文的重点是什么？",
                },
                headers={"X-Requested-With": "fetch"},
            )
            private_response = self.client.post(
                "/chat/send",
                data={
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "show_done": "",
                    "rel_path": "paper.pdf",
                    "tab": "source",
                    "visibility": "private",
                    "body": "只给我的复现建议是什么？",
                },
                headers={"X-Requested-With": "fetch"},
            )

        self.assertEqual(shared_response.status_code, 200)
        self.assertEqual(private_response.status_code, 200)
        shared_payload = shared_response.get_json()
        private_payload = private_response.get_json()
        assert shared_payload is not None
        assert private_payload is not None
        self.assertIn("团队共享回答", str(shared_payload["context"]))
        self.assertIn("私人回答", str(private_payload["context"]))

        admin_html = self.client.get("/?paper=paper.pdf&tab=source").get_data(as_text=True)
        self.assertIn("团队共享回答", admin_html)
        self.assertIn("私人回答", admin_html)
        self.assertIn("一起学", admin_html)
        self.assertIn("我爱学", admin_html)

        alice_html = alice_client.get("/?paper=paper.pdf&tab=source").get_data(as_text=True)
        self.assertIn("团队共享回答", alice_html)
        self.assertNotIn("私人回答", alice_html)

        context_response = self.client.get("/chat/context?paper=paper.pdf")
        self.assertEqual(context_response.status_code, 200)
        context_payload = context_response.get_json()
        assert context_payload is not None
        self.assertIn("团队共享回答", str(context_payload["shared"]))

    def test_team_shared_chat_renders_markdown_for_multiple_users(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Team Chat Paper")
        self.app.team_store.create_user("alice", "Alice", "alice-pass-123", "member")
        self.app.team_store.create_user("bob", "Bob", "bob-pass-123", "member")
        alice_client = self.app.test_client()
        bob_client = self.app.test_client()
        self.login_client_as(alice_client, "alice")
        self.login_client_as(bob_client, "bob")

        def complete_chat(**kwargs):
            self.app.team_store.update_chat_message(
                kwargs["assistant_message_id"],
                body=f"**Paper Bot 回复**\n- 面向 {kwargs['display_name']}\n- 渠道 {kwargs['visibility']}",
                status="completed",
                model="gpt-5.4",
            )

        with patch.object(self.app.chat_queue, "submit", side_effect=complete_chat):
            alice_shared = alice_client.post(
                "/chat/send",
                data={
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "show_done": "",
                    "rel_path": "paper.pdf",
                    "tab": "source",
                    "visibility": "shared",
                    "body": "Alice 的共享问题",
                },
                headers={"X-Requested-With": "fetch"},
            )
            bob_shared = bob_client.post(
                "/chat/send",
                data={
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "show_done": "",
                    "rel_path": "paper.pdf",
                    "tab": "source",
                    "visibility": "shared",
                    "body": "Bob 的共享问题",
                },
                headers={"X-Requested-With": "fetch"},
            )
            alice_private = alice_client.post(
                "/chat/send",
                data={
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "show_done": "",
                    "rel_path": "paper.pdf",
                    "tab": "source",
                    "visibility": "private",
                    "body": "Alice 的私有问题",
                },
                headers={"X-Requested-With": "fetch"},
            )

        self.assertEqual(alice_shared.status_code, 200)
        self.assertEqual(bob_shared.status_code, 200)
        self.assertEqual(alice_private.status_code, 200)

        alice_html = alice_client.get("/?paper=paper.pdf&tab=source").get_data(as_text=True)
        bob_html = bob_client.get("/?paper=paper.pdf&tab=source").get_data(as_text=True)
        alice_context = alice_client.get("/chat/context?paper=paper.pdf").get_json()
        bob_context = bob_client.get("/chat/context?paper=paper.pdf").get_json()

        assert alice_context is not None
        assert bob_context is not None
        self.assertIn("Alice 的共享问题", bob_html)
        self.assertIn("Bob 的共享问题", bob_html)
        self.assertIn("<strong>Paper Bot 回复</strong>", bob_html)
        self.assertIn("Alice 的私有问题", alice_html)
        self.assertNotIn("Alice 的私有问题", bob_html)
        self.assertIn("body_html", str(bob_context["shared"]))
        self.assertIn("<strong>Paper Bot 回复</strong>", str(bob_context["shared"]))
        self.assertIn("Alice 的私有问题", str(alice_context["private"]))
        self.assertNotIn("Alice 的私有问题", str(bob_context["private"]))

    def test_chat_send_route_returns_pending_context_for_async_polling(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Async Chat Paper")

        with patch.object(self.app.chat_queue, "submit", return_value=None) as mocked:
            response = self.client.post(
                "/chat/send",
                data={
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "show_done": "",
                    "rel_path": "paper.pdf",
                    "tab": "source",
                    "visibility": "private",
                    "body": "请总结这篇论文的核心贡献",
                },
                headers={"X-Requested-With": "fetch"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        assert payload is not None
        self.assertTrue(payload["ok"])
        self.assertIn("Paper Bot 正在思考...", str(payload["context"]["private"]))
        self.assertIn("pending", str(payload["context"]["private"]))
        mocked.assert_called_once()

        context_response = self.client.get("/chat/context?paper=paper.pdf")
        self.assertEqual(context_response.status_code, 200)
        context_payload = context_response.get_json()
        assert context_payload is not None
        self.assertIn("Paper Bot 正在思考...", str(context_payload["private"]))
        self.assertIn("pending", str(context_payload["private"]))

    def test_chat_context_eventually_shows_background_reply(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Background Chat Paper")

        def delayed_answer(*args, **kwargs):
            time.sleep(0.15)
            return "后台线程回答完成"

        with patch("src.paper_reader.chat_queue.answer_question_about_document", side_effect=delayed_answer):
            response = self.client.post(
                "/chat/send",
                data={
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "show_done": "",
                    "rel_path": "paper.pdf",
                    "tab": "source",
                    "visibility": "shared",
                    "body": "请给我一个简短总结",
                },
                headers={"X-Requested-With": "fetch"},
            )

            self.assertEqual(response.status_code, 200)
            initial_payload = response.get_json()
            assert initial_payload is not None
            self.assertIn("pending", str(initial_payload["context"]["shared"]))

            completed_payload = None
            for _ in range(40):
                poll = self.client.get("/chat/context?paper=paper.pdf")
                self.assertEqual(poll.status_code, 200)
                completed_payload = poll.get_json()
                assert completed_payload is not None
                if "后台线程回答完成" in str(completed_payload["shared"]):
                    break
                time.sleep(0.05)

        assert completed_payload is not None
        self.assertIn("后台线程回答完成", str(completed_payload["shared"]))
        self.assertIn("completed", str(completed_payload["shared"]))

    def test_index_lists_existing_pdf_docx_and_default_prompt(self) -> None:
        self.make_pdf(self.library / "2501.12948.pdf", "DeepSeek-R1")
        self.make_docx(self.library / "notes.docx", "RL Notes", "submitted on 25 Jan 2025")

        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("DeepSeek-R1", html)
        self.assertIn("RL Notes", html)
        self.assertIn("2025-01", html)
        self.assertIn("核心解读", html)

    def test_upload_saves_supported_file_and_triggers_auto_prompts(self) -> None:
        upload_bytes = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(upload_bytes)
        upload_bytes.seek(0)

        with patch.object(self.app.job_queue, "submit", return_value={"queued": 1, "existing": 0, "skipped": 0, "invalid": 0, "job_ids": [], "jobs": []}) as mocked:
            response = self.client.post(
                "/upload",
                data={
                    "target_folder": "arxiv/2025",
                    "files": (upload_bytes, "paper.pdf"),
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue((self.library / "arxiv" / "2025" / "paper.pdf").exists())
        mocked.assert_called_once_with(
            ["arxiv/2025/paper.pdf"],
            ["core-zh"],
            force=False,
            source="upload",
            requested_by_user_id=ANY,
            requested_by_display_name="admin",
        )

    def test_upload_file_endpoint_returns_json_for_single_success(self) -> None:
        upload_bytes = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(upload_bytes)
        upload_bytes.seek(0)

        with patch.object(self.app.job_queue, "submit", return_value={"queued": 1, "existing": 0, "skipped": 0, "invalid": 0, "job_ids": [], "jobs": []}) as mocked:
            response = self.client.post(
                "/upload-file",
                data={
                    "target_folder": "incoming",
                    "folder": "incoming",
                    "q": "",
                    "sort": "date_desc",
                    "file": (upload_bytes, "single.pdf"),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "saved")
        self.assertEqual(response.json["saved_rel_path"], "incoming/single.pdf")
        self.assertTrue(response.json["visible_in_current_view"])
        self.assertEqual(response.json["paper"]["file_name"], "single.pdf")
        mocked.assert_called_once_with(
            ["incoming/single.pdf"],
            ["core-zh"],
            force=False,
            source="upload",
            requested_by_user_id=ANY,
            requested_by_display_name="admin",
        )

    def test_upload_file_endpoint_skips_duplicate_content(self) -> None:
        original = io.BytesIO(b"same-content")
        duplicate = io.BytesIO(b"same-content")
        (self.library / "existing.pdf").write_bytes(original.getvalue())

        with patch.object(self.app.job_queue, "submit") as mocked:
            response = self.client.post(
                "/upload-file",
                data={
                    "target_folder": "",
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "file": (duplicate, "renamed.pdf"),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "duplicate")
        self.assertEqual(response.json["duplicate_rel_path"], "existing.pdf")
        self.assertFalse((self.library / "renamed.pdf").exists())
        mocked.assert_not_called()

    def test_upload_route_keeps_successful_files_when_some_fail(self) -> None:
        upload_bytes = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(upload_bytes)
        upload_bytes.seek(0)

        with patch.object(self.app.job_queue, "submit", return_value={"queued": 1, "existing": 0, "skipped": 0, "invalid": 0, "job_ids": [], "jobs": []}) as mocked:
            response = self.client.post(
                "/upload",
                data={
                    "target_folder": "mixed",
                    "folder": "mixed",
                    "q": "",
                    "sort": "date_desc",
                    "files": [
                        (upload_bytes, "ok.pdf"),
                        (io.BytesIO(b"bad"), "bad.txt"),
                    ],
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue((self.library / "mixed" / "ok.pdf").exists())
        self.assertFalse((self.library / "mixed" / "bad.txt").exists())
        mocked.assert_called_once_with(
            ["mixed/ok.pdf"],
            ["core-zh"],
            force=False,
            source="upload",
            requested_by_user_id=ANY,
            requested_by_display_name="admin",
        )

    def test_prompt_save_route_creates_custom_prompt(self) -> None:
        response = self.client.post(
            "/prompt-save",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "paper": "",
                "tab": "source",
                "name": "方法拆解",
                "slug": "method-breakdown",
                "model": "gpt-5.4",
                "enabled": "on",
                "auto_run": "on",
                "user_prompt": "请直接阅读 `{document_path}`，从实现角度解释这篇论文。",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("方法拆解", html)
        self.assertIsNotNone(self.app.prompt_store.get_prompt("method-breakdown"))

    def test_prompt_save_route_auto_generates_slug_for_chinese_name(self) -> None:
        first = self.client.post(
            "/prompt-save",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "paper": "",
                "tab": "source",
                "name": "实验摘要",
                "slug": "",
                "model": "gpt-5.4",
                "enabled": "on",
                "auto_run": "on",
                "user_prompt": "请直接阅读 `{document_path}`，总结实验部分。",
            },
            follow_redirects=True,
        )
        second = self.client.post(
            "/prompt-save",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "paper": "",
                "tab": "source",
                "name": "复现建议",
                "slug": "",
                "model": "gpt-5.4",
                "enabled": "on",
                "auto_run": "on",
                "user_prompt": "请直接阅读 `{document_path}`，给出复现建议。",
            },
            follow_redirects=True,
        )

        prompts = self.app.prompt_store.list_prompts()
        slugs = [prompt.slug for prompt in prompts]

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertIn("prompt", slugs)
        self.assertIn("prompt-2", slugs)
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_prompt_store_can_manage_multiple_prompts(self) -> None:
        self.app.prompt_store.save_prompt(
            existing_slug=None,
            name="方法拆解",
            slug="method-breakdown",
            user_prompt="请直接阅读 `{document_path}`，解释方法。",
            model="gpt-5.4",
            enabled=True,
            auto_run=True,
        )
        self.app.prompt_store.save_prompt(
            existing_slug=None,
            name="实验摘要",
            slug="experiment-summary",
            user_prompt="请直接阅读 `{document_path}`，解释实验。",
            model="gpt-5.4",
            enabled=False,
            auto_run=False,
        )

        prompts = self.app.prompt_store.list_prompts()
        names = [prompt.name for prompt in prompts]

        self.assertIn("核心解读", names)
        self.assertIn("方法拆解", names)
        self.assertIn("实验摘要", names)
        self.assertEqual(len(prompts), 3)

    def test_prompt_missing_tab_shows_empty_state(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Test Title")
        self.create_prompt("experiment-read", "实验摘要")

        response = self.client.get("/?paper=paper.pdf&tab=experiment-read")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("这份解读还没生成，所以这里暂时还是空的。", html)
        self.assertIn("实验摘要", html)

    def test_index_renders_compact_workspace_controls(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Compact Workspace")

        response = self.client.get("/?paper=paper.pdf&tab=source")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("workspace-orbit-dock", html)
        self.assertIn("workspace-like-button", html)
        self.assertIn("pane-restore-glyph", html)
        self.assertIn('role="toolbar"', html)
        self.assertIn("pane-restore-rail", html)
        self.assertIn('aria-controls="settings-drawer"', html)
        self.assertIn('role="dialog"', html)
        self.assertIn('aria-labelledby="settings-drawer-title"', html)
        self.assertIn('tabindex="-1"', html)
        self.assertIn('aria-hidden="true"', html)
        self.assertIn('aria-label="折叠阅读区"', html)
        self.assertIn("settings-user-card", html)
        self.assertIn('data-collapsible-toggle="tags-inline"', html)
        self.assertIn('data-collapsible-body="tags-inline"', html)
        self.assertIn("data-chat-form", html)
        self.assertIn("推荐列表与论文索引", html)
        self.assertIn("右边只显示一个聊天区域；点“我爱学”或“一起学”时，会直接切换到对应那一块。", html)
        self.assertIn('data-chat-switch="private"', html)
        self.assertIn('data-chat-panel="private"', html)
        self.assertIn('data-chat-panel="shared"', html)
        self.assertIn('id="chat-shared" hidden', html)
        self.assertIn("加入推荐列表", html)
        self.assertIn("发到一起学", html)
        self.assertIn("compact-tag-toggle", html)
        self.assertIn("原文阅读", html)
        self.assertNotIn("<strong>讨论</strong>", html)
        self.assertNotIn("把想法记在这里，后面的人能接着看", html)
        self.assertNotIn('name="reason"', html)
        self.assertNotIn("团队视角", html)

    def test_workspace_styles_support_dragging_and_mobile_collapses(self) -> None:
        css = (Path(self.app.static_folder) / "style.css").read_text(encoding="utf-8")

        self.assertIn("touch-action: none;", css)
        self.assertIn(
            ".workspace-shell.center-collapsed .viewer-head-flat,\n.workspace-shell.center-collapsed .viewer-inline-tags-panel,\n.workspace-shell.center-collapsed .viewer-tabs,\n.workspace-shell.center-collapsed [data-center-stage] {\n  display: none;",
            css,
        )
        self.assertIn(
            ".workspace-shell.left-collapsed .pane-left,\n  .workspace-shell.center-collapsed .pane-center,\n  .workspace-shell.right-collapsed .pane-right {\n    display: none;",
            css,
        )
        self.assertIn(
            "body.settings-open .settings-orb:not(.dragging) {\n  transform: rotate(8deg) scale(0.96);\n  z-index: 54;\n}",
            css,
        )

    def test_workspace_template_hides_collapsed_regions_from_keyboard_navigation(self) -> None:
        template = (Path(self.app.template_folder) / "index.html").read_text(encoding="utf-8")

        self.assertIn('pane.toggleAttribute("inert", collapsed);', template)
        self.assertIn('pane.setAttribute("aria-hidden", collapsed ? "true" : "false");', template)
        self.assertIn('settingsDrawer.toggleAttribute("inert", !layoutState.settingsOpen);', template)
        self.assertIn('settingsDrawer.setAttribute("aria-hidden", layoutState.settingsOpen ? "false" : "true");', template)

    def test_sidebar_groups_by_year_month_and_done_toggle(self) -> None:
        self.make_pdf(self.library / "2025-paper.pdf", "2025 Paper")
        self.make_docx(self.library / "2024-notes.docx", "2024 Notes", "submitted on 11 Dec 2024")

        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("paper-year-group", html)
        self.assertIn("2025", html)
        self.assertIn("2024-12", html)
        self.assertIn("显示 DONE 论文", html)

    def test_done_toggle_moves_file_and_hides_it_by_default(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Done Me")
        prompt = self.app.prompt_store.get_prompt("core-zh")
        assert prompt is not None
        result_path = self.app.library.prompt_result_path_for("paper.pdf", prompt.slug)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text("# Cached\n", encoding="utf-8")

        response = self.client.post(
            "/done-toggle",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "show_done": "",
                "tab": "source",
                "rel_path": "paper.pdf",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse((self.library / "paper.pdf").exists())
        self.assertTrue((self.library / "DONE" / "paper.pdf").exists())
        self.assertTrue(self.app.library.prompt_result_path_for("DONE/paper.pdf", prompt.slug).exists())
        self.assertNotIn("Done Me", html)

        show_done_response = self.client.get("/?show_done=1")
        self.assertIn("Done Me", show_done_response.get_data(as_text=True))

    def test_done_toggle_can_restore_paper(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Restore Me")
        done_path = self.app.library.toggle_done("paper.pdf")

        response = self.client.post(
            "/done-toggle",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "show_done": "1",
                "tab": "source",
                "rel_path": done_path,
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue((self.library / "paper.pdf").exists())
        self.assertFalse((self.library / done_path).exists())

    def test_scan_excludes_done_papers_by_default(self) -> None:
        self.make_pdf(self.library / "todo.pdf", "Todo")
        self.make_pdf(self.library / "done.pdf", "Done")
        self.app.library.toggle_done("done.pdf")

        default_scan = self.app.library.scan(force=True)
        full_scan = self.app.library.scan(force=True, include_done=True)

        default_names = [paper.file_name for paper in default_scan.papers]
        full_names = [paper.file_name for paper in full_scan.papers]

        self.assertIn("todo.pdf", default_names)
        self.assertNotIn("done.pdf", default_names)
        self.assertIn("done.pdf", full_names)

    def test_index_reads_from_persisted_active_index_without_rescanning_tree(self) -> None:
        self.make_pdf(self.library / "cached-paper.pdf", "Cached Paper")
        self.app.library.rebuild_active_index(lightweight=True)

        fresh_app = create_app(self.library)
        fresh_app.testing = True
        client = fresh_app.test_client()
        with client.session_transaction() as session:
            session["authenticated"] = True
            session["username"] = "admin"

        with patch.object(fresh_app.library, "iter_documents", side_effect=AssertionError("should not rescan tree")):
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("cached-paper.pdf", response.get_data(as_text=True))

    def test_include_done_scan_uses_done_index_instead_of_done_filesystem_walk(self) -> None:
        self.make_pdf(self.library / "todo.pdf", "Todo")
        self.make_pdf(self.library / "done.pdf", "Done")
        self.app.library.toggle_done("done.pdf")

        with patch.object(self.app.library, "iter_documents", wraps=self.app.library.iter_documents) as mocked:
            full_scan = self.app.library.scan(force=True, include_done=True)

        self.assertEqual([call.kwargs.get("include_done", False) for call in mocked.call_args_list], [False])
        self.assertEqual(sorted(paper.file_name for paper in full_scan.papers), ["done.pdf", "todo.pdf"])

    def test_done_index_updates_for_done_rename_and_delete(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Done Index")
        done_rel_path = self.app.library.toggle_done("paper.pdf")

        renamed_rel_path = self.app.library.rename_file(done_rel_path, "renamed.pdf")
        after_rename = self.app.library.scan(force=True, include_done=True)
        rename_names = [paper.file_name for paper in after_rename.papers]

        self.assertEqual(renamed_rel_path, "DONE/renamed.pdf")
        self.assertIn("renamed.pdf", rename_names)
        self.assertNotIn("paper.pdf", rename_names)

        self.app.library.delete_file(renamed_rel_path)
        after_delete = self.app.library.scan(force=True, include_done=True)
        self.assertNotIn("renamed.pdf", [paper.file_name for paper in after_delete.papers])

    def test_batch_section_hides_done_papers_even_when_show_done_enabled(self) -> None:
        self.make_pdf(self.library / "todo.pdf", "Todo Paper")
        self.make_pdf(self.library / "done.pdf", "Done Paper")
        self.app.library.toggle_done("done.pdf")

        response = self.client.get("/tool-panels/batch-run?show_done=1")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Todo Paper", html)
        self.assertNotIn("Done Paper", html)

    def test_batch_section_shows_select_all_controls(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Prompt Target")

        response = self.client.get("/tool-panels/batch-run")
        html = response.get_data(as_text=True)

        self.assertIn('data-check-action="all" data-check-group="prompt"', html)
        self.assertIn('data-check-action="all" data-check-group="paper"', html)
        self.assertIn('data-check-action="none" data-check-group="prompt"', html)
        self.assertIn('data-check-action="none" data-check-group="paper"', html)
        self.assertIn('data-batch-select-all', html)
        self.assertIn("全选全部匹配结果", html)
        self.assertIn("选择分析模板", html)
        self.assertIn("批量生成所选结果", html)

    def test_batch_section_can_optionally_include_done_papers(self) -> None:
        self.make_pdf(self.library / "todo.pdf", "Todo Paper")
        self.make_pdf(self.library / "done.pdf", "Done Paper")
        self.app.library.toggle_done("done.pdf")

        default_response = self.client.get("/tool-panels/batch-run")
        include_response = self.client.get("/tool-panels/batch-run?batch_show_done=1")

        default_html = default_response.get_data(as_text=True)
        include_html = include_response.get_data(as_text=True)

        self.assertEqual(default_response.status_code, 200)
        self.assertEqual(include_response.status_code, 200)
        self.assertIn("Todo Paper", default_html)
        self.assertNotIn("Done Paper", default_html)
        self.assertIn("Done Paper", include_html)

    def test_batch_section_paginates_large_result_sets(self) -> None:
        for index in range(55):
            self.make_pdf(self.library / f"paper-{index:02d}.pdf", f"Paper {index:02d}")

        first_response = self.client.get("/tool-panels/batch-run")
        second_response = self.client.get("/tool-panels/batch-run?batch_page=2")
        first_html = first_response.get_data(as_text=True)
        second_html = second_response.get_data(as_text=True)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertIn("共 55 篇", first_html)
        self.assertIn("第 1/2 页", first_html)
        self.assertIn("Paper 54", first_html)
        self.assertNotIn("Paper 04", first_html)
        self.assertIn("Paper 04", second_html)
        self.assertNotIn("Paper 54", second_html)

    def test_prompt_batch_route_can_select_all_filtered_papers_across_pages(self) -> None:
        for index in range(53):
            self.make_pdf(self.library / f"paper-{index:02d}.pdf", f"Paper {index:02d}")

        with patch.object(self.app.job_queue, "submit", return_value={"queued": 53, "existing": 0, "skipped": 0, "invalid": 0, "job_ids": [], "jobs": []}) as mocked:
            response = self.client.post(
                "/prompt-batch-run",
                data={
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "paper": "paper-52.pdf",
                    "tab": "source",
                    "batch_page": "2",
                    "select_all_filtered": "1",
                    "prompt_slugs": ["core-zh"],
                },
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        called_rel_paths = mocked.call_args.args[0]
        self.assertEqual(len(called_rel_paths), 53)
        self.assertIn("paper-00.pdf", called_rel_paths)
        self.assertIn("paper-52.pdf", called_rel_paths)

    def test_prompt_batch_route_select_all_filtered_includes_subfolders(self) -> None:
        for index in range(17):
            self.make_pdf(self.library / "root" / f"paper-{index:02d}.pdf", f"Root {index:02d}")
        for index in range(9):
            self.make_pdf(self.library / "root" / "nested" / f"nested-{index:02d}.pdf", f"Nested {index:02d}")

        with patch.object(self.app.job_queue, "submit", return_value={"queued": 26, "existing": 0, "skipped": 0, "invalid": 0, "job_ids": [], "jobs": []}) as mocked:
            response = self.client.post(
                "/prompt-batch-run",
                data={
                    "folder": "root",
                    "q": "",
                    "sort": "date_desc",
                    "paper": "root/paper-16.pdf",
                    "tab": "source",
                    "batch_page": "1",
                    "select_all_filtered": "1",
                    "prompt_slugs": ["core-zh"],
                },
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        called_rel_paths = mocked.call_args.args[0]
        self.assertEqual(len(called_rel_paths), 26)
        self.assertIn("root/paper-00.pdf", called_rel_paths)
        self.assertIn("root/nested/nested-08.pdf", called_rel_paths)

    def test_prompt_tab_renders_markdown_html(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Test Title")
        prompt = self.app.prompt_store.get_prompt("core-zh")
        assert prompt is not None
        result_path = self.app.library.prompt_result_path_for("paper.pdf", prompt.slug)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            "# 标题\n\n## 小节\n\n- 列表项\n\n包含 **加粗**、`code` 和 $E=mc^2$。\n\n<script>alert('x')</script>\n",
            encoding="utf-8",
        )

        response = self.client.get("/?paper=paper.pdf&tab=core-zh")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('<article class="markdown-viewer markdown-render">', html)
        self.assertIn("<h1>标题</h1>", html)
        self.assertIn("<h2>小节</h2>", html)
        self.assertIn("<strong>加粗</strong>", html)
        self.assertIn("<code>code</code>", html)
        self.assertIn("$E=mc^2$", html)
        self.assertIn("vendor/mathjax/tex-svg.js", html)
        self.assertIn("&lt;script&gt;alert", html)
        self.assertNotIn("<script>alert", html)

    def test_generate_prompt_result_skips_existing_markdown(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Test Title")
        prompt = self.app.prompt_store.get_prompt("core-zh")
        assert prompt is not None
        existing_path = self.app.library.prompt_result_path_for("paper.pdf", prompt.slug)
        existing_path.parent.mkdir(parents=True, exist_ok=True)
        existing_path.write_text("# Existing\n", encoding="utf-8")

        with patch("src.paper_reader.ai_summary.run_prompt_on_document", side_effect=AssertionError("should not run")):
            path, generated = self.app.library.generate_prompt_result("paper.pdf", prompt, force=False)

        self.assertFalse(generated)
        self.assertEqual(path, existing_path)

    def test_rename_and_delete_file_move_prompt_results(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Test Title")
        prompt = self.app.prompt_store.get_prompt("core-zh")
        assert prompt is not None
        result_path = self.app.library.prompt_result_path_for("paper.pdf", prompt.slug)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text("# Cached\n", encoding="utf-8")

        rename_response = self.client.post(
            "/rename",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "tab": prompt.slug,
                "rel_path": "paper.pdf",
                "new_name": "paper-renamed.pdf",
            },
            follow_redirects=True,
        )
        self.assertEqual(rename_response.status_code, 200)
        moved_result = self.app.library.prompt_result_path_for("paper-renamed.pdf", prompt.slug)
        self.assertTrue((self.library / "paper-renamed.pdf").exists())
        self.assertTrue(moved_result.exists())
        self.assertFalse(result_path.exists())

        delete_response = self.client.post(
            "/delete",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "rel_path": "paper-renamed.pdf",
            },
            follow_redirects=True,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse((self.library / "paper-renamed.pdf").exists())
        self.assertFalse(moved_result.exists())

    def test_prompt_batch_route_runs_selected_prompts(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Test Title")
        self.create_prompt("method-breakdown", "方法拆解")

        with patch.object(self.app.job_queue, "submit", return_value={"queued": 2, "existing": 0, "skipped": 1, "invalid": 0, "job_ids": [], "jobs": []}) as mocked:
            response = self.client.post(
                "/prompt-batch-run",
                data={
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "paper": "paper.pdf",
                    "tab": "source",
                    "rel_paths": ["paper.pdf"],
                    "prompt_slugs": ["core-zh", "method-breakdown"],
                },
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        mocked.assert_called_once_with(
            ["paper.pdf"],
            ["core-zh", "method-breakdown"],
            force=False,
            source="batch",
            requested_by_user_id=ANY,
            requested_by_display_name="admin",
        )

    def test_prompt_run_route_submits_background_job(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Test Title")

        with patch.object(self.app.job_queue, "submit", return_value={"queued": 1, "existing": 0, "skipped": 0, "invalid": 0, "job_ids": [], "jobs": []}) as mocked:
            response = self.client.post(
                "/prompt-run",
                data={
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "rel_path": "paper.pdf",
                    "prompt_slug": "core-zh",
                },
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        mocked.assert_called_once_with(
            ["paper.pdf"],
            ["core-zh"],
            force=False,
            source="manual",
            requested_by_user_id=ANY,
            requested_by_display_name="admin",
        )

    def test_serve_file_tolerates_zoom_fragment_encoded_in_path(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Zoom Safe")

        response = self.client.get("/files/paper.pdf%23zoom=page-width")
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")

    def test_offline_package_route_builds_complete_zip_bundle(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Offline PDF")
        self.make_docx(self.library / "notes.docx", "Offline Notes", "docx body for offline preview")
        self.create_prompt("method-breakdown", "方法拆解")

        core_prompt = self.app.prompt_store.get_prompt("core-zh")
        assert core_prompt is not None
        result_path = self.app.library.prompt_result_path_for("paper.pdf", core_prompt.slug)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text("# 离线摘要\n\n- 要点一\n", encoding="utf-8")

        response = self.client.post(
            "/offline-package",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "paper": "paper.pdf",
                "tab": "source",
                "rel_paths": ["paper.pdf", "notes.docx"],
            },
        )
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")

        archive = zipfile.ZipFile(io.BytesIO(response.data))
        names = set(archive.namelist())

        self.assertIn("index.html", names)
        self.assertIn("manifest.json", names)
        self.assertIn("assets/style.css", names)
        self.assertIn("assets/offline-reader.css", names)
        self.assertIn("assets/offline-reader.js", names)
        self.assertIn("assets/vendor/mathjax/tex-svg.js", names)
        self.assertIn("papers/paper.pdf", names)
        self.assertIn("papers/notes.docx", names)
        self.assertIn("prompt-results/paper.pdf/core-zh.md", names)

        index_html = archive.read("index.html").decode("utf-8")
        manifest_payload = archive.read("manifest.json").decode("utf-8")

        self.assertIn("论文离线阅读包", index_html)
        self.assertIn("offline-manifest", index_html)
        self.assertIn("assets/vendor/mathjax/tex-svg.js", index_html)
        self.assertIn("Offline PDF", manifest_payload)
        self.assertIn("Offline Notes", manifest_payload)

    def test_offline_package_route_ignores_done_papers(self) -> None:
        self.make_pdf(self.library / "todo.pdf", "Todo Export")
        self.make_pdf(self.library / "done.pdf", "Done Export")
        done_rel_path = self.app.library.toggle_done("done.pdf")

        response = self.client.post(
            "/offline-package",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "paper": "todo.pdf",
                "tab": "source",
                "rel_paths": ["todo.pdf", done_rel_path],
            },
        )
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        archive = zipfile.ZipFile(io.BytesIO(response.data))
        names = set(archive.namelist())

        self.assertIn("papers/todo.pdf", names)
        self.assertNotIn(f"papers/{done_rel_path}", names)

    def test_jobs_status_endpoint_returns_snapshot(self) -> None:
        self.make_pdf(self.library / "paper.pdf", "Test Title")
        with patch.object(self.app.job_queue, "snapshot", return_value={"jobs": [{"id": "job-1", "status": "queued"}], "active_count": 1, "queued_count": 1, "running_count": 0, "average_duration_seconds": 12.5, "max_concurrency": 32, "active_executions": 0}) as mocked:
            response = self.client.get("/jobs/status?paper=paper.pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["active_count"], 1)
        self.assertEqual(response.json["max_concurrency"], 32)
        mocked.assert_called_once_with(rel_path="paper.pdf")

    def test_job_snapshot_counts_all_queued_jobs_even_when_list_is_limited(self) -> None:
        rel_paths = []
        for index in range(65):
            rel_path = f"paper-{index:03d}.pdf"
            self.make_pdf(self.library / rel_path, f"Paper {index:03d}")
            rel_paths.append(rel_path)

        release = threading.Event()

        def slow_generate(rel_path, prompt, *, force=False, progress_callback=None, should_abort=None, process_callback=None):
            while not release.is_set():
                if should_abort and should_abort():
                    raise InterruptedError("Job interrupted.")
                time.sleep(0.02)
            return self.app.library.prompt_result_path_for(rel_path, prompt.slug), True

        with patch.object(self.app.library, "generate_prompt_result", side_effect=slow_generate):
            self.app.job_queue.submit(rel_paths, ["core-zh"], force=True, source="batch")
            for _ in range(100):
                snapshot = self.app.job_queue.snapshot(limit=32)
                if snapshot["active_count"] == 65:
                    break
                time.sleep(0.02)
            release.set()

        self.assertEqual(snapshot["active_count"], 65)
        self.assertEqual(snapshot["queued_count"] + snapshot["running_count"], 65)
        self.assertEqual(len(snapshot["jobs"]), 32)

    def test_job_queue_defaults_to_12_workers(self) -> None:
        self.assertEqual(self.app.job_queue.max_concurrency, 12)
        self.assertEqual(len(self.app.job_queue._workers), 32)

    def test_jobs_config_route_updates_max_concurrency(self) -> None:
        response = self.client.post(
            "/jobs/config",
            data={
                "folder": "",
                "q": "",
                "sort": "date_desc",
                "paper": "",
                "tab": "source",
                "max_concurrency": "7",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.app.job_queue.max_concurrency, 7)
        self.assertEqual(self.app.settings_store.max_concurrency(), 7)

    def test_jobs_stop_all_route_interrupts_running_and_queued_jobs(self) -> None:
        self.make_pdf(self.library / "paper-a.pdf", "Paper A")
        self.make_pdf(self.library / "paper-b.pdf", "Paper B")
        self.app.job_queue.update_max_concurrency(1)

        started = threading.Event()
        release = threading.Event()

        def slow_generate(rel_path, prompt, *, force=False, progress_callback=None, should_abort=None, process_callback=None):
            started.set()
            while not release.is_set():
                if should_abort and should_abort():
                    raise InterruptedError("Job interrupted.")
                time.sleep(0.02)
            return self.app.library.prompt_result_path_for(rel_path, prompt.slug), True

        with patch.object(self.app.library, "generate_prompt_result", side_effect=slow_generate):
            self.app.job_queue.submit(["paper-a.pdf", "paper-b.pdf"], ["core-zh"], force=True, source="batch")
            self.assertTrue(started.wait(timeout=2))

            for _ in range(100):
                snapshot = self.app.job_queue.snapshot()
                if snapshot["running_count"] == 1 and snapshot["queued_count"] >= 1:
                    break
                time.sleep(0.02)

            response = self.client.post(
                "/jobs/stop-all",
                data={
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "paper": "",
                    "tab": "source",
                },
                follow_redirects=True,
            )
            release.set()

        self.assertEqual(response.status_code, 200)
        for _ in range(100):
            snapshot = self.app.job_queue.snapshot()
            if snapshot["active_count"] == 0:
                break
            time.sleep(0.02)
        statuses = {job.status for job in self.app.job_queue.list_jobs(limit=10)}
        self.assertIn("stopped", statuses)

    def test_reindex_route_uses_lightweight_scan_without_metadata_extraction(self) -> None:
        (self.library / "manual-added.pdf").write_bytes(b"%PDF-1.4\n")
        done_dir = self.library / "DONE"
        done_dir.mkdir(parents=True, exist_ok=True)
        (done_dir / "manual-done.pdf").write_bytes(b"%PDF-1.4\n")

        before = self.app.library.scan(force=True, include_done=True)
        self.assertNotIn("manual-done.pdf", [paper.file_name for paper in before.papers])

        with patch("src.paper_reader.document_utils.extract_document_metadata", side_effect=AssertionError("should not extract")):
            response = self.client.post(
                "/reindex",
                data={
                    "folder": "",
                    "q": "",
                    "sort": "date_desc",
                    "paper": "",
                    "tab": "source",
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        cached = self.app.library.scan()
        names = [paper.file_name for paper in cached.papers]
        self.assertIn("manual-added.pdf", names)
        with_done = self.app.library.scan(force=True, include_done=True)
        self.assertIn("manual-done.pdf", [paper.file_name for paper in with_done.papers])

    def test_index_shows_sources_button_in_bottom_tools(self) -> None:
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("查看来源归档", html)
        self.assertIn("/sources", html)

    def test_sources_page_lists_archived_day_and_paper(self) -> None:
        self.create_source_day("2026-04-11", paper_id="2604.08377", title="SkillClaw")

        response = self.client.get("/sources")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("每日论文来源", html)
        self.assertIn("2026-04-11", html)
        self.assertIn("SkillClaw", html)
        self.assertIn("2604.08377", html)
        self.assertIn("打包下载选中论文", html)
        self.assertIn("导入到阅读器", html)

    def test_sources_download_zip_packages_selected_papers(self) -> None:
        self.create_source_day("2026-04-11", paper_id="2604.08377", title="SkillClaw")

        response = self.client.post(
            "/sources/download-zip",
            data={"run_date": "2026-04-11", "paper_ids": ["2604.08377"]},
        )
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")
        archive = zipfile.ZipFile(io.BytesIO(response.data))
        names = set(archive.namelist())
        self.assertIn("manifest.json", names)
        self.assertTrue(any(name.endswith(".pdf") for name in names))

    def test_sources_import_copies_pdf_into_library_and_submits_auto_prompts(self) -> None:
        self.create_source_day("2026-04-11", paper_id="2604.08377", title="SkillClaw")

        with patch.object(
            self.app.job_queue,
            "submit",
            return_value={"queued": 1, "existing": 0, "skipped": 0, "invalid": 0, "job_ids": [], "jobs": []},
        ) as mocked:
            response = self.client.post(
                "/sources/import",
                data={"run_date": "2026-04-11", "paper_ids": ["2604.08377"]},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        imported = self.library / "Sources" / "HuggingFace" / "2026" / "04" / "11" / "2604.08377.pdf"
        self.assertTrue(imported.exists())
        mocked.assert_called_once_with(
            ["Sources/HuggingFace/2026/04/11/2604.08377.pdf"],
            ["core-zh"],
            force=False,
            source="source-import",
            requested_by_user_id=ANY,
            requested_by_display_name="admin",
        )

    def test_render_markdown_supports_rule_and_blockquote(self) -> None:
        rendered = render_markdown("# 标题\n\n> 引用内容\n\n---\n\n1. 第一项\n2. 第二项")

        self.assertIn("<h1>标题</h1>", rendered)
        self.assertIn("<blockquote><p>引用内容</p></blockquote>", rendered)
        self.assertIn("<hr>", rendered)
        self.assertIn("<ol><li>第一项</li><li>第二项</li></ol>", rendered)

    def test_render_markdown_preserves_math_blocks_and_strips_answer_wrapper(self) -> None:
        rendered = render_markdown("<answer>\n\n$$\nE = mc^2\n$$\n\n行内公式 $a^2+b^2=c^2$。\n\n</answer>")

        self.assertNotIn("&lt;answer&gt;", rendered)
        self.assertIn('<div class="math-block">$$\nE = mc^2\n$$</div>', rendered)
        self.assertIn("<p>行内公式 $a^2+b^2=c^2$。</p>", rendered)

    def test_render_markdown_keeps_html_like_inline_code_readable(self) -> None:
        rendered = render_markdown("答案放在 `<answer></answer>` 里。")

        self.assertIn("<p>答案放在 <code>&lt;answer&gt;&lt;/answer&gt;</code> 里。</p>", rendered)
        self.assertNotIn("&amp;lt;answer&amp;gt;", rendered)


if __name__ == "__main__":
    unittest.main()
