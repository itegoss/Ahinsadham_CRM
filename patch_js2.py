import os
import re

file_path = r"c:\Users\Varsha\Ahinsadham\Ahinsadham-main\heart_charity\templates\welcome.html"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace the previous handlePaginationSelect with a new version that uses localStorage
# and also intercepts pagination <a> clicks and form submissions!

new_js = """
<script>
  function handlePaginationSelect(selectElement) {
    const pageNum = selectElement.value;
    const pageParam = selectElement.name;
    const urlParams = new URLSearchParams(window.location.search);
    urlParams.set(pageParam, pageNum);
    
    const activeTab = localStorage.getItem('activeTab');
    if (activeTab) {
      urlParams.set('active_tab', activeTab);
    }
    
    window.location.href = "?" + urlParams.toString();
  }

  document.addEventListener("DOMContentLoaded", function() {
    // Intercept native form submissions for pagination
    document.querySelectorAll('form.pagination-form').forEach(form => {
      form.addEventListener('submit', function(e) {
        e.preventDefault();
        const formData = new FormData(this);
        const urlParams = new URLSearchParams(window.location.search);
        
        for (const [key, value] of formData.entries()) {
          urlParams.set(key, value);
        }
        
        const activeTab = localStorage.getItem('activeTab');
        if (activeTab) {
          urlParams.set('active_tab', activeTab);
        }
        
        window.location.href = "?" + urlParams.toString();
      });
    });

    // Intercept pagination links to inject correct activeTab
    document.querySelectorAll('.pagination-form').forEach(form => {
        // Find sibling <a> tags which are pagination buttons
        const parent = form.parentElement;
        if (parent) {
            parent.querySelectorAll('a.btn').forEach(link => {
                link.addEventListener('click', function(e) {
                    if (this.getAttribute('href')) {
                        e.preventDefault();
                        const href = this.getAttribute('href');
                        const url = new URL(href, window.location.origin + window.location.pathname);
                        
                        const activeTab = localStorage.getItem('activeTab');
                        if (activeTab) {
                            url.searchParams.set('active_tab', activeTab);
                        }
                        window.location.href = url.pathname + url.search;
                    }
                });
            });
        }
    });
  });
</script>
{% endblock %}
"""

# Find where we inserted the old script
if "function handlePaginationSelect(selectElement) {" in content:
    # We replace from <script>\n  function handlePaginationSelect up to {% endblock %} at the end
    pattern = r'<script>\s*function handlePaginationSelect.*?{% endblock %}'
    content = re.sub(pattern, new_js.strip(), content, flags=re.DOTALL)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Fixed JS logic")
else:
    print("Could not find previous JS")
