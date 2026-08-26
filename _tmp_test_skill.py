import subprocess, json, pathlib

# Test text-to-image skill
skill_path = pathlib.Path(r'C:\Users\hot_m\.codex\skills\text-to-image')
print('skill exists:', skill_path.exists())
if skill_path.exists():
    for p in skill_path.rglob('*.md'):
        print('SKILL:', p.name, p.stat().st_size)

# Try running the skill
result = subprocess.run(
    ['python', '-m', 'text_to_image', '--help'],
    capture_output=True, text=True, timeout=30,
    cwd=str(skill_path)
)
print('stdout:', result.stdout[:500])
print('stderr:', result.stderr[:500])
