import os
from datetime import datetime, timezone
from urllib.parse import urlparse
from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from heart_charity.models import Lookup


class AhinsadhamStaticSitemap(Sitemap):
    """
    Sitemap for publicly accessible, indexable pages of Ahinsadham.
    Only includes the NGO homepage, schemes catalogue, and public donation form.
    Strictly excludes internal CRM, authentication, user data, and dynamic admin endpoints.
    """
    protocol = "https"

    PAGES = [
        {
            "name": "home",
            "changefreq": "daily",
            "priority": 1.0,
            "template": os.path.join("heart_charity", "templates", "home.html"),
        },
        {
            "name": "schemes",
            "changefreq": "weekly",
            "priority": 0.9,
            "template": os.path.join("heart_charity", "templates", "ACHschemas.html"),
        },
        {
            "name": "donation_form",
            "changefreq": "weekly",
            "priority": 0.9,
            "template": os.path.join("heart_charity", "templates", "ACHdonation.html"),
        },
    ]

    def items(self):
        return [p["name"] for p in self.PAGES]

    def location(self, item):
        return reverse(item)

    def changefreq(self, item):
        for p in self.PAGES:
            if p["name"] == item:
                return p["changefreq"]
        return "monthly"

    def priority(self, item):
        for p in self.PAGES:
            if p["name"] == item:
                return p["priority"]
        return 0.5

    def lastmod(self, item):
        """
        Return reliable modification timestamp if available:
        - For schemes: latest updated_at from charity scheme Lookups if available,
          or template file modification time.
        - For home & donation_form: template file last modified timestamp.
        """
        try:
            if item == "schemes":
                latest_scheme = Lookup.objects.filter(is_deleted=False).order_by("-updated_at").first()
                if latest_scheme and latest_scheme.updated_at:
                    return latest_scheme.updated_at

            # Fall back to template mtime if file exists
            base_dir = getattr(settings, "BASE_DIR", None)
            if base_dir:
                for p in self.PAGES:
                    if p["name"] == item:
                        template_rel = p.get("template")
                        if template_rel:
                            full_path = os.path.join(base_dir, template_rel)
                            if os.path.exists(full_path):
                                mtime = os.path.getmtime(full_path)
                                return datetime.fromtimestamp(mtime, tz=timezone.utc)
        except Exception:
            pass
        return None

    def get_domain(self, site=None):
        """
        Guarantee canonical HTTPS domain from settings.SITE_URL
        (defaulting to 'admin.ahinsadham.org').
        Prevents leaking localhost or testing URLs into production sitemaps.
        """
        site_url = getattr(settings, "SITE_URL", "https://admin.ahinsadham.org")
        parsed = urlparse(site_url)
        return parsed.netloc or "admin.ahinsadham.org"
