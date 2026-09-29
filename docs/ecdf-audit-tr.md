# Bölmesiz eCDF karşılaştırması — v0.15

Önceki [Rayleigh-model deneyi](rayleigh-coverage-tr.md), model doğru olsa bile
mekânsal bağıntıda %95 aralık iddiasını doğrulamadı. Bu adımda dağılım ailesi
varsaymadan, histogram bölmelerinden bağımsız bir **tek eşikli ayırma ölçüsü**
denendi. Schlunk ve Byram'ın [eCDF yaklaşımı](https://doi.org/10.1109/TUFFC.2023.3289157)
temel alındı. İki ampirik kümülatif dağılım farkının en büyük ve en küçük
değerleri arasındaki fark hesaplanır. Popülasyon yoğunlukları yalnızca bir kez
kesişiyorsa bu, teorik gCNR'ye eşittir. Birden çok kesişimde genel gCNR'nin
yerini tutmaz: örneğin hedef `{0,2}`, arka plan `{1,3}` ayrık desteklerinde
yoğunluk örtüşmesi sıfır ve gCNR 1 iken tek eşik farkı 0,5'tir.

## Kontrollü deney

Her senaryoda **200 bağımsız sentetik zarf alanı** kullanıldı (tohum `20261005`).
Önceki deneydeki sabit dairesel ROI ve analitik popülasyon gCNR değerleri
korundu. Rayleigh ve aynı şekilli lognormal çiftlerin ikisi de tek yoğunluk
kesişimine sahiptir. eCDF ve mevcut 64 bölmeli histogramın nokta tahmin yanlılığı
karşılaştırıldı. Ayrıca iki eCDF için Dvoretzky–Kiefer–Wolfowitz eşzamanlı
bantları ve farkın aralık fonksiyonu için muhafazakâr 95% sınır hesaplandı.
Bu sınır **her bölge içindeki gözlemler bağımsızsa** geçerlidir; grupların
birbirinden bağımsız olması gerekmez.

| Veri / örnekleme | eCDF yanlılığı | Histogram yanlılığı | Gözlenen DKW kapsaması | Ortalama aralık genişliği |
|---|---:|---:|---:|---:|
| Bağımsız Rayleigh pikselleri | +0,020 | +0,020 | 200/200 | 0,629 |
| 4×4 bağıntılı Rayleigh, pikseller | +0,114 | +0,279 | 197/200 | 0,623 |
| Aynı alan, bilinen kaynak hücrelerinden birer örnek | +0,098 | +0,239 | 200/200 | 1,000 |
| Bağımsız lognormal pikseller | +0,021 | +0,012 | 200/200 | 0,629 |

Bağıntılı piksellerin 197/200 kapsaması bir güvence **değildir**: DKW'nin
bağımsızlık koşulu ihlal edildi. Bilinen 4×4 kaynak hücrelerinden tek örnek
alınan kontrol matematiksel koşula uyar, fakat 95% sınırın tamamı `[0,1]`
olduğu için pratik bilgi taşımaz. Histogram lognormal örnekte daha az yanlıdır;
eCDF her koşulda üstün değildir. eCDF'nin sonlu örneklem yanlılığı da vardır.
Bu deneyler gerçek doku benzetimi veya klinik doğrulama değildir.

## Gerçek cihaz fantomu

[PICMUS/USTB kontrast fantomunun](real-data-provenance.md) gerçek RF kanal
verisi 11 açılı kanal-analitik CPWC ile işlendi; ayrıca UFF'ye gömülü görüntü
referansı aynı gridde ölçüldü. F/1,7, 2× grid seyreltilmesi, 8 açılı parti,
sığ/derin 15/43 mm kist merkezleri, 1,5 mm hedef ve 2,5–4,5 mm arka plan
halkası sabittir. Kaynak SHA-256, açı indeksleri ve ROI değerleri [ham ölçüm
kaydında](../artifacts/ecdf_study/metrics.json) bulunmaktadır.

| Görüntü | Kist | eCDF tek eşik | 64 bölmeli gCNR |
|---|---:|---:|---:|
| Analitik 11 açı | 15 mm | 0,940 | 0,928 |
| Analitik 11 açı | 43 mm | 0,931 | 0,926 |
| Gömülü UFF referansı | 15 mm | 0,975 | 0,972 |
| Gömülü UFF referansı | 43 mm | 0,938 | 0,934 |

Fantomun popülasyon gCNR'si ve tek-kesişim özelliği bilinmez. Bu sayılar
betimseldir; klinik tanısallık, referansa karşı mutlak doğruluk veya fantom
için %95 güven aralığı değildir. Üretim hattındaki 64-bölmeli metrik ve
varsayılan ışın oluşturucu değiştirilmedi.

```bash
python -m pip install -e ".[dev,accelerated]"
ultrasound-ecdf-study --trials 200 --seed 20261005 \
  --phantom-path data/raw/PICMUS_experiment_contrast_speckle.uff
python -m pytest tests/test_ecdf_study.py
```

Fantom dosyası indirilmemişse `--phantom-path` olmadan yalnızca sentetik
deney çalışır. [Üretilen tablo ve grafik](../artifacts/ecdf_study/README.md),
[tüm alan kayıtları](../artifacts/ecdf_study/metrics.json).

Gerçek RF üzerinde ilk duyarlılık takibi [v0.16 aktarım raporunda](ecdf-transfer-tr.md)
yapıldı. Bu çalışma da nüfus düzeyinde bir kalibrasyon veya geçerli %95 aralık
oluşturmadı.
