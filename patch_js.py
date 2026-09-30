import os

file_path = r"c:\Users\Varsha\Ahinsadham\Ahinsadham-main\heart_charity\templates\welcome.html"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

script_to_add = """
<script>
  function handlePaginationSelect(selectElement) {
    const pageNum = selectElement.value;
    const pageParam = selectElement.name; // e.g., "lt_page"
    
    const urlParams = new URLSearchParams(window.location.search);
    urlParams.set(pageParam, pageNum);
    
    // Maintain active_tab if it is in context but not in URL
    {% if active_tab %}
    if (!urlParams.has('active_tab')) {
      urlParams.set('active_tab', '{{ active_tab|escapejs }}');
    }
    {% endif %}
    
    window.location.href = "?" + urlParams.toString();
  }
</script>
{% endblock %}
"""

# Check if script is already present
if "function handlePaginationSelect" not in content:
    # Replace the last occurrence of {% endblock %}
    parts = content.rsplit("{% endblock %}", 1)
    if len(parts) == 2:
        content = parts[0] + script_to_add
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("Script added successfully.")
    else:
        print("Error: Could not find {% endblock %} at the end of the file.")
else:
    print("Script already present.")
