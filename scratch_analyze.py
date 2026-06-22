with open('heart_charity/templates/welcome.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = []
found_start = -1
for i, line in enumerate(lines):
    if 'document.addEventListener("input", function (event) {' in line:
        # Check if the next line or nearby contains "column-search"
        is_search = False
        for offset in range(1, 5):
            if i + offset < len(lines) and 'column-search' in lines[i + offset]:
                is_search = True
                break
        if is_search:
            found_start = i
            out.append(f"Found input event listener starting at line {i+1}")
            # print 25 lines
            for j in range(i, min(len(lines), i + 25)):
                out.append(f"{j+1}: {lines[j].strip()}")
            break

with open('scratch_output17.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
