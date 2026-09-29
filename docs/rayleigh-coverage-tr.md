# gCNR aralıkları: sonraki araştırma adımının sonucu (v0.14)

## Neyi sınadık?

Önceki [kapsama deneyi](../artifacts/coverage/README.md), 64 bölmeli histogram
gCNR için nominal %95 aralıklarının sentetik Rayleigh zarflarda bile eksik kapsama
verdiğini gösterdi. Bu sürümde, dağılımın **gerçekten Rayleigh olduğu varsayımıyla**
her ROI için ölçek parametresini `sqrt(mean(envelope²)/2)` ile tahmin ettik.
İki Rayleigh yoğunluğunun analitik örtüşmesinden gCNR'yi hesapladık. İşlem,
[Schlunk ve Byram'ın histogram hassasiyeti ve parametrik seçenekler
incelemesiyle](https://lab.vanderbilt.edu/beamlab/wp-content/uploads/sites/191/2024/04/schlunk_2023_gcnr.pdf)
uyumludur. Bu özel kestirici ve aşağıdaki kapsama deneyi projemizin uygulamasıdır.

Aralıkları, önceden belirlenen ROI içindeki dolu uzamsal blokları tekrar seçerek
hesapladık. Her koşulda 200 bağımsız alan ve aralık başına 300 tekrar örneği var.
Bilinen 4×4 bağımlılık deseninde 4×4 blok sınırının 2 piksel kayık olduğunu
üretici geometri belirler; gerçek görüntüde bunu bildiğimizi varsayamayız.
Bağımsız pikseller, kayık 4×4 bağımlı pikseller ve **Rayleigh olmayan** lognormal
veri ayrı ayrı sınandı. Rayleigh gCNR gerçek değeri 0,472470; lognormal gerçek
değeri 0,379474. Lognormal gerçek değer ayrı analitik formülle hesaplandı.

| Bağımsız son doğrulama, tohum 20261003 | Yüzdelik aralık | Basic aralık |
|---|---:|---:|
| Rayleigh, bağımsız pikseller, 1×1 | %96,0 | %96,0 |
| Rayleigh, 4×4 bağımlılık, 1×1 | %31,5 | %31,0 |
| Rayleigh, 4×4 bağımlılık, doğru hizalı 4×4 | **%89,0** | %88,0 |
| Lognormal, bağımsız pikseller, 1×1 | %45,0 | %41,5 |

**Sonuç:** Rayleigh modeli histogram yanlılığını bu kontrollü durumda belirgin
ölçüde azaltıyor. Buna rağmen bağımlı piksel koşulunda %95 kapsamaya ulaşmıyor.
Ölçek modeli yanlışsa tekrar çöküyor. `basic` bootstrap aralığı bu iki sorunu
çözmedi. Bu nedenle ölçülmüş insan/fantom görüntülerindeki gCNR hesabı
değiştirilmedi; eski aralıklar hâlâ kalibre edilmiş güven aralığı olarak
yorumlanmamalı. Tıbbi veya hasta düzeyinde çıkarım yapılmıyor.

## Deney ayrımı ve tekrarlama

- [İlk geliştirme seti](../artifacts/rayleigh_coverage/README.md), tohum 20261001:
  Rayleigh kestiricisi ve 1/8 blokları, 200 alan/senaryo. %93 bağımsız,
  %89 hizalı 8×8; sonuçlar görüldükten sonra gerçek 4×4 ölçek ayrıca eklendi.
- [Hizalama denemesi](../artifacts/rayleigh_coverage_validation/README.md),
  tohum 20261002: 4×4 hizalı blok %91,5; basic aralık henüz eklenmemişti.
- [Bağımsız son kontrol](../artifacts/rayleigh_coverage_final/README.md),
  tohum 20261003: 4×4 hizalı blok yüzdelik %89, basic %88.
  Bu yeni tohum, son yöntemi sabitledikten sonra üretildi. Wilson %95
  aralıkları ve tüm tekrar kayıtları JSON'dadır.

```bash
python -m pip install -e ".[dev,accelerated]"
ultrasound-rayleigh-coverage --seed 20261003 \
  --output-dir artifacts/rayleigh_coverage_final
python -m pytest tests/test_rayleigh_coverage.py
```

Bu çalışmada sentetik zarflar kullanılır; yeni ham hasta verisi veya RF çekimi
üretilmedi. Rayleigh varsayımının ölçülmüş veride sağlandığı gösterilmedi.
Gelecek yöntem geliştirmesi için ayrı veri ve önceden belirlenmiş kapsama
eşiği gerekir; bu deneyin başarısız olduğu koşullardan ayar seçilmemeli.
