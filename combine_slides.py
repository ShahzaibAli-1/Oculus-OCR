"""Combines slides_part1-4.html into a single slides_all.html."""
import re

files = [
    'slides_part1.html',
    'slides_part2.html',
    'slides_part3.html',
    'slides_part4.html',
]

all_styles = []
all_slides_html = []

for fname in files:
    with open(fname, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract everything inside <style>...</style>
    m = re.search(r'<style>(.*?)</style>', content, re.DOTALL)
    if m:
        all_styles.append(m.group(1).strip())

    # Extract everything inside <div class="deck" ...>...</div><!-- /deck -->
    m = re.search(r'<div class="deck"[^>]*>(.*?)</div>\s*<!--\s*/deck\s*-->', content, re.DOTALL)
    if m:
        all_slides_html.append(m.group(1).strip())

combined_css    = '\n\n'.join(all_styles)
combined_slides = '\n\n'.join(all_slides_html)

# Make sure only slide 1 carries the "active" class
# (part1 already has it; parts 2-4 should not have active slides, but just in case)
combined_slides = combined_slides.replace(' class="slide active"', ' class="slide"', )
# Re-add active to the very first slide
combined_slides = combined_slides.replace('class="slide"', 'class="slide active"', 1)

js = r"""
const slides=document.querySelectorAll('.slide');
const dotsEl=document.getElementById('dots');
const counter=document.getElementById('counter');
let cur=0;
slides.forEach((_,i)=>{
  const d=document.createElement('div');
  d.className='dot'+(i===0?' on':'');
  d.onclick=()=>go(i);
  dotsEl.appendChild(d);
});
function go(n){
  slides[cur].classList.remove('active');
  dotsEl.children[cur].classList.remove('on');
  cur=(n+slides.length)%slides.length;
  slides[cur].classList.add('active');
  dotsEl.children[cur].classList.add('on');
  counter.textContent=String(cur+1).padStart(2,'0')+' / '+String(slides.length).padStart(2,'0');
}
function move(d){go(cur+d)}
document.addEventListener('keydown',e=>{
  if(e.key==='ArrowRight'||e.key==='ArrowDown'||e.key===' ')move(1);
  if(e.key==='ArrowLeft'||e.key==='ArrowUp')move(-1);
});
""".strip()

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ocular — Full Presentation (32 Slides)</title>
  <style>
{combined_css}
  </style>
</head>
<body>
<div class="deck">
{combined_slides}
</div><!-- /deck -->

<!-- ── BOTTOM BAR ── -->
<div class="bottom-bar">
  <div class="slide-counter" id="counter">01 / 32</div>
  <div class="dots" id="dots"></div>
  <div class="nav">
    <button id="prev" onclick="move(-1)">&#8592;</button>
    <button id="next" onclick="move(1)">&#8594;</button>
  </div>
</div>

<script>
{js}
</script>
</body>
</html>"""

with open('slides_all.html', 'w', encoding='utf-8') as f:
    f.write(html)

# Count slides for verification
slide_count = len(re.findall(r'class="slide[" ]', html))
print(f"Done! slides_all.html created with {slide_count} slides.")
