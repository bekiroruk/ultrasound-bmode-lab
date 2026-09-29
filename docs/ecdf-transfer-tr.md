# eCDF varsayımı ve uzamsal doku: gerçek RF aktarımı — v0.16

[v0.15 sentetik ve fantom deneyi](ecdf-audit-tr.md), bölmesiz tek-eşik eCDF
ölçüsünün kimi koşullarda histogram yanlılığını azalttığını, fakat bağıntılı
görüntüler için kullanışlı bir %95 aralık üretmediğini gösterdi. Bu adımda
önceden açık veri olarak alınmış gerçek kanal RF kayıtlarıyla varsayımın
**duyarlılığı** incelendi; kalibrasyon veya klinik doğrulama yapılmadı.

## Kayıtlar ve sabit protokol

- EPFL gönüllü **005** ve **008** birbirinden ayrı iki insan kaydıdır. PICMUS
  karotid enine görünümünün kişi kimliği açıklanmadığı için üçüncü bağımsız
  katılımcı sayılmaz.
- PICMUS kontrast fantomunun 15 ve 43 mm derinlikli kistleri ayrı ROI'dir,
  fakat **aynı fiziksel taramadan** gelir.
- Karotid kayıtlarında tüm mevcut açılar (PICMUS 75; EPFL 87), fantomda 11
  açı; kanal-analitik CPWC, F/1,7, 8 açılı parti ve 2× grid seyreltilmesi.
  Lumen hedefi ve +1/+3 mm arka plan halkası kullanıldı. PICMUS ROI'si
  gömülü UFF referansından, EPFL ROI'leri aynı taramanın tam-açılı
  görüntüsünden önceden tanımlı heuristikle seçildi. EPFL'de seçim yanlılığı
  sürer. Fantomda nominal 1,5 mm hedef ve 2,5–4,5 mm halka sabittir.

Her ROI'de [Schlunk ve Byram'ın eCDF fikrine](https://doi.org/10.1109/TUFFC.2023.3289157)
dayanan tek-eşik ayrımı, mevcut 64 bölmeli gCNR ve 16/32/64 eşit-havuz-sıra
bölmeli yoğunluk-farkı tanısı hesaplandı. Arka plan halkasının log-zarf
dokusunda eksen bazlı, yalnızca maske içindeki çiftlerden Pearson
otokorelasyonu hesaplandı. İlk 1/e eşiği geçişi fiziksel mm'ye dönüştürüldü.
[Ultrason speckle otokorelasyonuna dair deneysel temel](https://scholars.duke.edu/publication/914472)
bu niceliğin araştırılmasını motive eder; burada kullanılan heterojen insan
halkalarında bunu bağımsız örnek aralığına çevirecek bir model **yoktur**.

| Kayıt / ROI | eCDF tek eşik | 64 bölmeli gCNR | Sıra-TV 16/32/64 | İşaret değişimi 16/32/64 | Eksenel/yatay 1/e mm |
|---|---:|---:|---|---|---:|
| PICMUS karotid enine | 0,596 | 0,546 | 0,593 / 0,593 / 0,598 | 1 / 1 / 3 | 1,397 / 1,276 |
| EPFL 005 | 0,506 | 0,502 | 0,500 / 0,540 / 0,580 | 1 / 7 / 15 | 1,285 / 1,455 |
| EPFL 008 | 0,534 | 0,516 | 0,528 / 0,557 / 0,611 | 1 / 7 / 13 | 1,024 / 3,833 |
| Fantom 15 mm kist | 0,940 | 0,928 | 0,933 / 0,933 / 0,933 | 1 / 1 / 1 | 0,275 / 0,302 |
| Fantom 43 mm kist | 0,931 | 0,926 | 0,908 / 0,925 / 0,926 | 1 / 1 / 1 | 0,284 / 0,308 |

Fantomdaki ayrı nominal homojen speckle diskinin (10, 28 mm; yarıçap 3 mm)
1/e geçişleri **0,280 / 0,303 mm** oldu; iki kist halkasının yaklaşık
0,28 / 0,30 mm değerleriyle tutarlı. İnsan halkalarında damar duvarı ve
başka doku sınırları bulunduğundan çok daha uzun 1/e değerleri bir saf
speckle korelasyon uzunluğu veya önerilen bootstrap blok boyutu değildir.

## Sahte çoklu-kesişim kontrolü

Her ROI'nin hedef/arka plan piksel sayılarına eşit örneklerle 100 kez IID
Rayleigh (ölçek 0,5 / 1,0) çiftleri üretildi; bunların popülasyon yoğunlukları
kesin olarak **tek kez** kesişir. Yine de 64 bölmeli deneyde işaret değişimi
ortancası PICMUS için 6, EPFL 005 için 15, EPFL 008 için 17 oldu. Gerçek
EPFL sayıları 15 ve 13'tür. Bu kontrol gerçek doku modeli, hipotez testi veya
p-değeri değildir; yalnızca sonlu örneklemin ek geçişler yaratabileceğini
gösterir. Dolayısıyla gerçek görüntülerde tek-eşik varsayımının sağlandığı
**ya da bozulduğu** kanıtlanmış değildir. Farklı bölme sayılarındaki
Sıra-TV–eCDF ayrışması da kestirim duyarlılığıdır, popülasyon doğrusu değil.

Veri SHA-256'ları, açı indeksleri, ROI'ler, ikili korelasyon eğrileri ve
kontrolün 5–95. yüzdelikleri [makine tarafından okunabilir raporda](../artifacts/ecdf_transfer/metrics.json).
[ROI çizimleri ve grafikler](../artifacts/ecdf_transfer/README.md) görsel
denetim içindir. Ham insan RF'si Git'e eklenmedi.

```bash
python -m pip install -e ".[dev,accelerated]"
ultrasound-ecdf-transfer --data-dir data/raw \
  --output-dir artifacts/ecdf_transfer
python -m pytest tests/test_ecdf_transfer.py
```

Sonraki karar: bu verilerden bir %95 aralık ya da otomatik blok seçimi
çıkarmamak. Böyle bir iddia için bağımsız ek taramalar, önceden dondurulmuş
homojen ROI politikası, geçerli bağıntı modeli ve dış doğrulamada kapsama
deneyi gerekir. Üretim hattındaki histogram ölçüsü değiştirilmedi.
