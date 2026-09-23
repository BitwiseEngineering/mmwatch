"""Blog posts are Markdown that load_posts() renders to HTML; the post template
must emit that HTML, not escape it.

Found 2026-09-23 by a fixture that rendered a post: the live page at
/blog/why-mmwatch-exists.html showed literal &lt;p&gt; tags as text, because
`post.html` interpolated a plain str under Jinja autoescape. The body is the
only HTML field; title and summary come from the same file but are plain text,
so they must stay escaped -- and summary lands inside an attribute.
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

    def test_summary_is_escaped_inside_the_meta_description(self):
        """summary is rendered into <meta name="description" content="..."> by
        base.html -- an attribute, where one unescaped quote breaks out of the
        tag. The h1 is the safe context; this is the dangerous one."""
        page = render_post(summary='He said "no" to the levy')
        self.assertIn('content="He said &#34;no&#34; to the levy"', page)


class RealPostsTest(unittest.TestCase):
    def test_the_real_posts_render_their_markdown(self):
        """The production path, load_posts() -> render_site(): the plain str
        from markdown.markdown() must survive |safe, and this fails loudly if
        the markdown package goes missing -- load_posts() then returns [] and
        the deploy would publish an empty blog with CI green."""
        posts = build.load_posts()
        self.assertTrue(posts, "no posts loaded from content/posts/")
        with tempfile.TemporaryDirectory() as tmp:
            build.render_site({}, posts, out=tmp, now=NOW)
            path = os.path.join(tmp, "blog", posts[0].slug + ".html")
            with open(path, encoding="utf-8") as fh:
                page = fh.read()
        body = page[page.index('<article class="post">'):]
        self.assertIn("<p>", body)
        self.assertNotIn("&lt;p&gt;", body)


if __name__ == "__main__":
    unittest.main()
