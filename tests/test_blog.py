"""Blog posts are Markdown that load_posts() renders to HTML; the post template
must emit that HTML, not escape it.

Found 2026-09-23 by a fixture that rendered a post: the live page at
/blog/why-mmwatch-exists.html showed literal &lt;p&gt; tags as text, because
`post.html` interpolated a plain str under Jinja autoescape. The body is the
ONLY trusted field -- it comes from our own content/posts/*.md -- so the title
and summary must stay escaped.
"""
import datetime
import os
import tempfile
import unittest

from mmwatch import build
from mmwatch.build import Post

NOW = datetime.datetime(2026, 9, 23, 8, 0)


def render_post(**kw):
    kw.setdefault("slug", "p")
    kw.setdefault("title", "A post")
    kw.setdefault("date", NOW.date())
    kw.setdefault("summary", "Summary.")
    kw.setdefault("html", "<p>Body with <em>emphasis</em>.</p>")
    with tempfile.TemporaryDirectory() as tmp:
        build.render_site({}, [Post(**kw)], out=tmp, now=NOW)
        with open(os.path.join(tmp, "blog", kw["slug"] + ".html"), encoding="utf-8") as fh:
            return fh.read()


class PostRenderTest(unittest.TestCase):
    def test_post_body_html_is_emitted_not_escaped(self):
        page = render_post()
        self.assertIn("<p>Body with <em>emphasis</em>.</p>", page)
        self.assertNotIn("&lt;p&gt;", page)

    def test_post_title_is_still_escaped(self):
        """Trusting the body must not leak into the other fields."""
        page = render_post(title="Budget & <levy>")
        self.assertIn("<h1>Budget &amp; &lt;levy&gt;</h1>", page)


if __name__ == "__main__":
    unittest.main()
