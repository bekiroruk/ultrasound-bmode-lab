"""Build an offline, single-file evidence demo from versioned scientific artifacts."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_portfolio(root=ROOT):
    artifacts = root / "artifacts"
    sequence = json.loads((artifacts / "sequence/metrics.json").read_text(encoding="utf-8"))
    native = json.loads((artifacts / "native_profile/metrics.json").read_text(encoding="utf-8"))
    coverage = json.loads((artifacts / "coverage/metrics.json").read_text(encoding="utf-8"))
    panels = [
        ("human", "İnsan RF verisi", "analytic_quality/PICMUS_carotid_cross_75_angles.png",
         ("Aynı gerçek insan RF kaydı: eski zarf yolu, kanal-analitik DAS ve UFF referansı. "
         "Referans benzerliği, tanısal doğruluk değildir.")),
        ("phantom", "Fiziksel fantom", "interpolation_study/contrast_interpolation.png",
         "Gerçek cihaz/fantom kaydı. Kübik gecikme, tüm ölçütlerde evrensel kazanç sağlamaz."),
        ("coverage", "Belirsizlik sınırı", "coverage/coverage.png",
         ("Bilinen Rayleigh dağılımlı sentetik zarflar; RF veya hasta verisi değildir. "
         "Gözlenen kapsama nominal %95'in altında: mevcut aralıklar kalibre değildir.")),
        ("sequence", "200 RF kare", "sequence/frames.png",
         ("SWE L7 cihaz dizisinden beş seçilmiş kare; örnek türü doğrulanmamıştır. "
         "Dosyadan sıralı işleme testi; canlı cihaz ve gerçek çekim hızı iddiası yoktur.")),
        ("latency", "Süre / bellek", "sequence/profile.png",
         ("200 kare tek tek okunur; kareler arasında analitik önbellek taşınmaz. "
         "RSS kare sonlarında örneklenir, geçici bellek tepesini ölçmez.")),
        ("native", "C++ aktarımı", "native_profile/profile.png",
         ("C++17/OpenMP hüzme oluşturma; Hilbert ve sıkıştırma Python/SciPy'da. "
         "Bu makinede C++ prototipi Numba'dan yavaş; aktarılabilirlik kanıtı, hız üstünlüğü değil.")),
    ]
    tabs, sections = [], []
    for index, (key, title, filename, caption) in enumerate(panels):
        encoded = base64.b64encode((artifacts / filename).read_bytes()).decode("ascii")
        selected = "true" if index == 0 else "false"
        tabs.append(f'<button role="tab" id="tab-{key}" aria-controls="{key}" '
                    f'aria-selected="{selected}" onclick="showPanel(\'{key}\')">'
                    f'{html.escape(title)}</button>')
        hidden = "" if index == 0 else " hidden"
        sections.append(f'<section role="tabpanel" id="{key}" aria-labelledby="tab-{key}"{hidden}>'
                        f'<h2>{html.escape(title)}</h2><p>{html.escape(caption)}</p>'
                        f'<img src="data:image/png;base64,{encoded}" alt="{html.escape(caption)}">'
                        '</section>')
    cpp_checks = (len(native["cpp_numba_agreement"]) + len(native["cpp_numpy_agreement"])
                  + len(native["sequence_cpp_numpy_agreement"]))
    title = "Ultrasound B-mode Lab | Bekir Oruk"
    page = f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{font-family:system-ui,Segoe UI,sans-serif;color:#e6edf5;background:#101923}}
*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1200px;margin:auto;padding:32px 20px}}
.eyebrow{{color:#62d5c5;font-weight:700;letter-spacing:.13em;font-size:12px}}
h1{{font-size:clamp(30px,5vw,54px);margin:10px 0}}h2{{font-size:24px}}
p{{line-height:1.7;color:#bbcada}}a{{color:#77d7ec}}
.notice{{border-left:4px solid #e6b56b;background:#242d38;padding:14px 18px;color:#f4ddb9}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:24px 0}}
.card{{padding:18px;border:1px solid #354457;border-radius:12px;background:#172432}}
.card strong{{display:block;font-size:28px;color:#72d7c6}}.card span{{font-size:13px;line-height:1.6}}
nav{{display:flex;flex-wrap:wrap;gap:8px;margin:22px 0}}
button{{font:inherit;color:#d2deed;background:#1d2c3d;border:1px solid #40556c;border-radius:8px;
padding:10px 14px;cursor:pointer}}button[aria-selected=true]{{background:#64d1c1;color:#10202b}}
button:focus-visible{{outline:3px solid #f5bf69;outline-offset:3px}}
section{{border:1px solid #354457;border-radius:12px;padding:20px;background:#172432}}
section img{{width:100%;height:auto;background:white;border-radius:8px}}
footer{{font-size:13px;border-top:1px solid #354457;margin-top:24px;padding-top:18px}}
.flow{{padding:18px;border-radius:10px;background:#213243;line-height:2;font-family:monospace}}
</style></head><body><main>
<div class="eyebrow">BEKİR ORUK · ARAŞTIRMA PORTFÖYÜ · v0.13</div>
<h1>RF kaydından<br>B-mod görüntüye.</h1>
<p>Ölçülmüş insan ve fantom verisi, açıklanabilir algoritmalar, sayısal doğrulama ve gerçek hız ölçümleri.
Bu çevrimdışı demo önceden hesaplanmış sonuçları gösterir; tarayıcıda yeniden oluşturma yapmaz.</p>
<div class="notice">Araştırma / eğitim yazılımı. Tıbbi cihaz değildir; tanı veya tedavi için kullanılamaz.
İnsan kayıtları dört farklı hasta ya da doğrulanmış hastalık vakası anlamına gelmez.</div>
<div class="cards">
<div class="card"><strong>4 + 3</strong><span>insan RF kaydı + fiziksel fantom kaydı<br>Ek SWE dizisi: örnek türü belirsiz</span></div>
<div class="card"><strong>{sequence['frame_count']} kare</strong><span>256×128, analitik kübik DAS<br>
Ortanca {sequence['median_ms']:.1f} ms · p95 {sequence['p95_ms']:.1f} ms</span></div>
<div class="card"><strong>{cpp_checks} kontrol</strong><span>C++ / Numba / NumPy ölçülmüş RF eşdeğerliği<br>8 CPU iş parçacığı</span></div>
<div class="card"><strong>{coverage['settings']['trials_per_scenario']} × 2</strong><span>bağımsız sentetik alan<br>
Belirsizlik kapsamı: sınırlar bulundu</span></div></div>
<div class="flow">RF + cihaz geometrisi → kanal Hilbert → kesirli gecikme → ağırlıklı toplama
→ açı birleştirme → zarf → log sıkıştırma → B-mod / ölçütler</div>
<nav role="tablist" aria-label="Deney kanıtları">{''.join(tabs)}</nav>
{''.join(sections)}
<h2>Mühendislik sonucu</h2>
<p>Görüntü güzelliği tek başına başarı ölçütü değil. Kanal-analitik işleme çizgilenmeyi azaltıyor;
açıklık ve kübik enterpolasyon kalite/maliyet ödünleşimi getiriyor. Belirsizlik deneyi aralıkların
kalibre olmadığını gösteriyor. C++ prototipi sayısal olarak uyuşuyor ama bu ölçümde daha hızlı değil.</p>
<footer>
<a href="../../docs/portfolio-tr.md">Mülakat anlatımı ve kapsam</a> ·
<a href="../coverage/README.md">Kapsama raporu</a> ·
<a href="../sequence/README.md">Kare testi</a> ·
<a href="../native_profile/README.md">C++ ölçümleri</a> ·
<a href="https://github.com/bekiroruk/ultrasound-bmode-lab">GitHub kaynak kodu</a>
<p>Grafikler gömülüdür; internet ve ham veri gerekmez. Rapor bağlantıları depo klasöründe çalışır.
Veri kaynakları: USTB/PICMUS, EPFL Ultrafast Ultrasound Dataset ve USTB SWE L7.
Kaynak ve lisanslar: <a href="../../docs/real-data-provenance.md">veri kökeni</a>.</p>
</footer></main><script>
function showPanel(id) {{
  document.querySelectorAll('[role=tabpanel]').forEach(p => p.hidden = p.id !== id);
  document.querySelectorAll('[role=tab]').forEach(b => b.setAttribute('aria-selected',
    String(b.getAttribute('aria-controls') === id)));
}}
document.querySelectorAll('[role=tab]').forEach((button, index, buttons) => {{
  button.addEventListener('keydown', event => {{
    let next;
    if(event.key === 'ArrowRight') next = (index+1) % buttons.length;
    else if(event.key === 'ArrowLeft') next = (index+buttons.length-1) % buttons.length;
    else if(event.key === 'Home') next = 0;
    else if(event.key === 'End') next = buttons.length-1;
    else return;
    event.preventDefault(); buttons[next].focus(); buttons[next].click();
  }});
}});
</script></body></html>"""
    output = artifacts / "portfolio"
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text(page, encoding="utf-8")
    (output / "README.md").write_text(
        "# Offline evidence demo\n\nOpen `index.html` locally in a browser. "
        "All six scientific figures are embedded; no server, download or raw dataset is required. "
        "This is a precomputed evidence viewer, not real-time reconstruction.\n\n"
        "Rebuild: `python scripts/build_portfolio.py` after the coverage, sequence and native "
        "profile commands. Supporting Markdown links work inside the repository checkout.\n",
        encoding="utf-8")
    return output / "index.html"


if __name__ == "__main__":
    print(build_portfolio())
