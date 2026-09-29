# Ultrasound B-mode Lab — proje özeti

## Güncel araştırma notu — v0.16

[Gerçek RF eCDF ve uzamsal doku aktarımı](ecdf-transfer-tr.md) iki ayrı EPFL
gönüllüsü, PICMUS karotid kesiti ve fiziksel fantom üzerinde tamamlandı.
Başlangıçta tanımlanan dört portföy paketi v0.13'te bitmişti; [çevrimdışı demo](../artifacts/portfolio/README.md)
şimdi v0.16 kanıtlarıyla sekiz panele güncellendi ve kaynak-hash manifesti içeriyor.
EPFL'de ince sıra bölmelerinde çok işaret değişimi görüldü; gerçek dağılımları
tek-kesişimli olan eş-örneklemli sentetik kontrol de benzer değişimler üretti.
Fantomun homojen speckle kontrolü yaklaşık 0,28/0,30 mm 1/e doku ölçeği
verdi. İnsan halkaları heterojendir; bu sayılar bağımsız örnek sayısına
veya güven aralığı kalibrasyonuna dönüştürülmedi.

## Önceki araştırma notu — v0.15

[Bölmesiz eCDF deneyi](ecdf-audit-tr.md) ve ölçülmüş PICMUS fantom
karşılaştırması tamamlandı. Tek eşikli eCDF ölçüsü sentetik bağıntılı
Rayleigh alanında histogram yanlılığını azalttı; bağıntı farkındalıklı
muhafazakâr aralık ise `[0,1]` genişliğinde ve kullanışsız kaldı.
Fantomda yalnızca betimsel nokta tahminleri raporlandı. Varsayılan metrik
ve klinik olmayan araştırma kapsamı değişmedi.

## Önceki araştırma notu — v0.14

[gCNR belirsizlik takibi](rayleigh-coverage-tr.md) tamamlandı. Rayleigh
varsayımı altında yeni tahmin bağımsız alanlarda %96 kapsamaya ulaştı; gerçek
4×4 bağımlılığa hizalanan bloklarda son bağımsız kontrolde %89, lognormal
dağılımda %45 kaldı. Genel bir kalibrasyon elde edilmedi. Ölçülmüş görüntü
ölçütü ve araştırma portföyünün v0.13 sonuçları değiştirilmedi.

## Güncel durum — v0.13

Son dört portföy adımı tamamlandı: kontrollü kapsama deneyi, 200 gerçek RF karelik
dosya oynatma testi, C++ analitik/kübik odaklama ve çevrimdışı demo.
[Teslim özeti ve mülakat anlatımı](portfolio-tr.md) güncel giriş noktasıdır.

Kapsama deneyi aralıkların kalibre olmadığını gösterdi; C++ bu hostta Numba'dan daha
yavaş çıktı. Yeni SWE L7 dizisi 200 × 1 × 128 × 1664 boyutundadır; doğrulanmış insan
verisi olarak sayılmaz. Önceki dört insan + üç fantom kaydına ek ayrı bir cihaz dizisidir.
İşleme ortancası 19,29 ms; p95 22,85 ms. Klinik veya canlı cihaz iddiası yoktur.
Önceki sürüm bölümleri tarihsel deney kayıtlarıdır.

Bu proje, ultrason cihazlarından alınmış açık erişimli RF kanal kayıtlarından B-mod görüntü
oluşturan ve algoritma değişikliklerini tekrarlanabilir deneylerle değerlendiren bir araştırma
yazılımıdır. Ana çalışma Python/NumPy ve hızlandırılmış Numba CPU üzerinde yürür. Görüntü
kalitesi, çalışma süresi ve bellek kullanımı birlikte ele alınır.

## Veri gerçekten nereden geliyor?

| Kaynak | Projede kullanılan kayıt | Veri türü ve kapsam |
|---|---|---|
| USTB/PICMUS | Karotid enine ve boyuna görüntüleme: 2 kayıt | Gerçek insan ölçümü; Verasonics ve L11/L11-4v. İki görünümün farklı kişilere ait olduğu belirtilmiyor. |
| EPFL Ultrafast Ultrasound Dataset | Gönüllü 005 ve 008: kişi başına 1 karotid kaydı | Açık kimliği farklı 2 gönüllü; GE 9L-D ve araştırma amaçlı Verasonics ölçümleri. |
| USTB/PICMUS | Kontrast/speckle ve çözünürlük/distorsiyon: 2 kayıt | CIRS 040GSE fiziksel fantomun cihazla ölçülmüş RF verisi. |
| USTB/Alpinion | Hipokoik fantom: 1 kayıt | Alpinion L3-8 ile fiziksel fantom ölçümü. |

Toplam **4 insan kaydı ve 3 fiziksel fantom kaydı** vardır. Bu sayı, dört farklı hasta veya
tanısı doğrulanmış dört vaka anlamına gelmez. Kimlikleri birbirinden açıkça ayrılan gönüllü
sayısı EPFL alt kümesinde ikidir. Fantom, özellikleri değerlendirmeye uygun fiziksel bir test
nesnesidir; burada fantom RF kayıtları da gerçek cihaz ölçümleridir.

Veriler Kaggle ekran görüntülerinden değil, USTB/Zenodo ve EPFL kaynaklarından alınır. Ham
dosyalar Git'e eklenmez. İndirme araçları dosya bütünlüğünü denetler; deney raporları kaynak
SHA-256 değerlerini, prob geometrisini ve kullanılan ayarları kaydeder. Sentetik veriler ayrıca
algoritma ve sınır koşulu testlerinde kullanılır. Kaynaklar, lisanslar ve zorunlu atıflar için
[veri kökeni](real-data-provenance.md) ve [izlenebilirlik](configuration-traceability.md).

## Görüntü nasıl oluşuyor?

Ölçülmüş RF kanalları ve cihaz bilgileri okunur. Analitik işleme yolunda Hilbert dönüşümü
kanalların özgün zaman örnekleri üzerinde yapılır. Her görüntü noktası için gönderim ve alım
uçuş süresi hesaplanır; kesirli gecikmeler doğrusal veya kübik enterpolasyonla örneklenir.
Derinliğe bağlı alım açıklığı ve ağırlıklandırma uygulanır. Kanallar ve seçilen gönderim
açıları faz bilgisi korunarak toplanır. Kompleks sonucun büyüklüğü zarfı verir; logaritmik
sıkıştırma B-mod görüntüyü oluşturur.

Analitik sinyal, taban banda indirilmiş IQ değildir. Eski yolun kaba görüntü ızgarası üzerinde
zarf çıkarması düşey çizgilenmeye neden olabiliyordu; kanal üzerinde analitik işleme bu soruna
yönelik temel düzeltmedir. Güncel karşılaştırmalarda 60 dB görüntüleme aralığı kullanılır.
Filtreleme, kazanç kontrolü ve gürültü azaltma deneyleri ayrıca bulunur; her rapor uyguladığı
işlemleri belirtir. Ayrıntılar: [algoritma tasarımı](algorithm-design.md).

## Sürümler boyunca yapılanlar

| Aşama | Tamamlanan geliştirme ve değerlendirme |
|---|---|
| v0.1 | Temel RF→B-mod zinciri, sentetik deneyler ve PICMUS gerçek RF okuma/yeniden oluşturma. |
| v0.2 | DAS, CF, PCF, DMAS ve MVDR karşılaştırmaları; açı sayısı deneyleri; fiziksel fantom ölçümleri; görüntü işleme deneyleri; Numba hızlandırma ve karotid ilgi bölgesi analizi. |
| v0.3 | İki EPFL gönüllüsü ve Alpinion fantomu ile farklı kayıt/prob kontrolleri; fiziksel açıya göre seçim ve veri bütünlüğü denetimleri. |
| v0.4 | Kanallar üzerinde analitik işleme; çizgilenme sorununun incelenmesi ve aynı UFF referansına karşı önce/sonra karşılaştırmaları. |
| v0.5 | Sabit bölgelerde kontrast, CNR, gCNR ve eksenel/yatay FWHM ölçümleri; harici kayıtlarda analitik işleme ve ızgara tutarlılığı. |
| v0.6 | Alım açıklığı/F-sayısı taraması; görüntü kalitesi ödünleşimleri; ayrı çalışma süresi ve bellek profili. |
| v0.7 | Fantomda seçilen F/0.8'in insan/harici kayıtlara aktarım kontrolü; açıları küçük gruplarda işleyerek geçici belleği azaltma ve sayısal eşdeğerlik. |
| v0.8 | Aynı RF kaydında yinelenen işlemler için analitik kanal önbelleği; hazırlama maliyeti, bellek bedeli ve tekrar süresi ölçümleri. |
| v0.9 | NumPy/Numba kübik gecikme enterpolasyonu; kontrollü sinüs testi; iki gerçek fantomda doğrusal/kübik karşılaştırması ve 1460–1620 m/s ses hızı duyarlılığı. |
| v0.10 | Sabit ayarlarla kübik enterpolasyonun beş insan/fantom kaydına aktarımını ve doğrusal/kübik zaman-bellek maliyetini değerlendiren tekrarlanabilir araçlar. Sayısal sonuçlar aşağıdaki sürüme ait raporlarda tutulur. |

Önemli mühendislik sonucu: her değişiklik her ölçütü iyileştirmez. Analitik işleme fantom
kontrastını ve eksenel çözünürlüğü iyileştirirken yatay FWHM genişlemiştir. Fantomda daha dar
yatay FWHM veren F/0.8, insan UFF referanslarına benzerliği artırmamıştır. Kübik enterpolasyon
v0.9 fantom ölçütlerinde küçük kazançlar sağlamış, referans SSIM'ini her durumda yükseltmemiştir.
v0.10 insan kayıtlarında da evrensel bir kazanç görülmemiştir: örneğin 75 açılı PICMUS enine
görünümünde SSIM 0,7152'den 0,7061'e düşmüştür. Aynı koşullardaki hız ölçümünde kübik hesap
11 açıda %37,2, 75 açıda %27,1 daha uzun sürmüştür; örneklenen bellek tepe değerleri yaklaşık
321 MiB düzeyindedir. On aktarım eşdeğerlik kontrolü ve 84 otomatik test geçmiştir.
Bu nedenle sonuçlar varsayılan ayarların otomatik değiştirilmesi için yeterli görülmemiştir.

İlgili kanıtlar: [analitik fantom doğrulaması](../artifacts/analytic_validation/phantom/README.md),
[açıklık aktarımı](../artifacts/aperture_transfer/README.md),
[önbellek profili](../artifacts/cache_profile/README.md),
[v0.9 enterpolasyon/ses hızı çalışması](../artifacts/interpolation_study/README.md).

## v0.10 deneylerini yeniden çalıştırma

Depo kökünde, sanal ortam etkin ve [ana README'deki](../README.md#reproduce-the-complete-study)
veri indirmeleri tamamlanmışken:

```bash
python -m pip install -e ".[dev,accelerated,datasets]"
ultrasound-interpolation-transfer --data-dir data/raw --output-dir artifacts/interpolation_transfer
ultrasound-interpolation-profile --dataset data/raw/PICMUS_carotid_cross.uff --output-dir artifacts/interpolation_profile --repeats 5 --threads 8
```

Aktarım deneyi iki PICMUS insan görünümünü, iki EPFL gönüllüsünü ve Alpinion fantomunu kapsar.
F/1.7, cihaz kaydındaki ses hızı, analitik işleme ve önbellekli 8 açılık gruplar sabittir.
11 açı ve mevcut tüm açılar karşılaştırılır. Her kübik sonuç ayrıca önbelleksiz ve
gruplandırılmamış kübik hesapla aynı koordinatlarda doğrulanır.

Profil deneyi tek PICMUS karotid kaydında, 11/75 açı için doğrusal ve kübik yöntemi aynı
ayarlarla ölçer. Süreler, ısınma işlemi dışarıda tutularak ayrı süreçlerde alınır; bellek
örneklemesi ayrı geçişte yapılır. Donanım ve çalışma koşulları değişince mutlak süreler de
değişebilir; sürümler arasındaki farklı ölçüm oturumları doğrudan hızlanma hesabına katılmaz.

- [v0.10 aktarım raporu ve görüntüler](../artifacts/interpolation_transfer/README.md)
- [v0.10 çalışma süresi/bellek raporu](../artifacts/interpolation_profile/README.md)

## Sonuçları hangi sınırlar içinde anlatmalıyız?

UFF içindeki görüntü, aynı ölçümün algoritmik referansıdır; anatomik veya tanısal doğruluk
etiketi değildir. EPFL/Alpinion için bağımsız referans bulunmadığından v0.10 referans skorları
boş bırakılır. Doğrusal ve kübik görüntülerin birbirine benzerliği yalnız değişim miktarını
gösterir. Aynı yöntemin 11/tüm açı karşılaştırması da seyrek açı tutarlılığını ölçer.

FWHM noktasal hedefin görüntüdeki genişliğini, gCNR hedef ve arka plan dağılımlarının
ayrışmasını değerlendirir. Birindeki kazanç tüm görüntünün veya klinik performansın daha iyi
olduğunu tek başına kanıtlamaz. Az sayıda kayıt ve daha önce incelenmiş verilerle yapılan bu
çalışmalar, yeni bir kör klinik değerlendirme değildir. Eski ROI bootstrap aralıkları da
kişiler arası belirsizliği temsil etmez.

## Sonraki sınırlı iş paketleri

v0.11'de ilk paketin tek kayıt üzerindeki kısmı tamamlandı:
[analitik damar bölgesi raporu](../artifacts/analytic_roi/README.md). Aynı damar bölgesinde
eski, analitik-doğrusal ve analitik-kübik yöntemler 11/75 açıyla karşılaştırıldı. Her yöntem
aynı blok örneklerini aldı; 1, 4, 8 ve 16 piksellik bloklar için 500'er tekrar yapıldı.
75 açıda kontrast -15,67 dB'den analitik-doğrusal hesapta -19,00 dB'ye değişirken gCNR
0,587'den 0,546'ya düştü. Yani sonuç bütün ölçütlerde iyileşme değil.
Bloklar büyüyünce belirsizlik aralıkları genişledi; bunlar klinik güven aralıkları değildir.

v0.12'de [ROI/blok başlangıç duyarlılığı](../artifacts/roi_sensitivity/README.md) tamamlandı:
PICMUS ve mevcut EPFL gönüllü 005 kaydı üzerinde merkez ±0,5 mm, yarıçap ±0,3 mm ve dört
blok başlangıcı denendi. Her kayıt için 10 koşul ve koşul başına 500 tekrar kullanıldı.
Dört karşılaştırmanın üçünde kübik–doğrusal gCNR farkının işareti bölge seçimiyle değişti.
Her karşılaştırmanın dört blok başlangıcında da fark aralığı sıfırı içerdi. EPFL bölgesi
önceden görülen tam-açılı doğrusal görüntüden elle sabitlendi; uzman etiketi veya bağımsız
referans değildir. Daha çok koşul denemek daha çok hasta doğrulamak anlamına gelmez.

1. Kontrollü, bilinen dağılımlı veride belirsizlik aralıklarının gerçek kapsamasını ölçmek;
   bölge/blok başlangıcının birlikte değişmesini ve farklı uzman bölge seçimlerini değerlendirmek.
2. Gerçek RF kare dizileriyle sürekli işleme, kare başına gecikme ve bellek kararlılığını
   ölçmek; mevcut açı gruplamasını disk/cihaz akışıyla çalışan bir tasarıma genişletmek.
3. Uygun donanımda GPU veya C++ yolunu derleyip analitik/kübik yöntemle eşdeğerliğini ve
   uçtan uca maliyetini ölçmek. Depodaki CUDA ve C++ kaynakları bu doğrulamayı tamamlamış
   sayılmaz; FPGA aktarımı yapılmamıştır.
4. Daha fazla kişi, cihaz ve klinik uzman değerlendirmesiyle bağımsız doğrulama tasarlamak.
   Canlı cihaz entegrasyonu, klinik doğrulama ve ürünleştirme tamamlanmış değildir.

Gereksinim, test, risk ve veri izlenebilirliği belgeleri mühendislik çalışmasını destekler;
proje bitmiş bir medikal cihaz veya mevzuata uygunluğu doğrulanmış bir ürün değildir.

## Mülakatta kısa anlatım

“Açık erişimli insan ve fiziksel fantom RF ölçümlerinden B-mod görüntü oluşturan bir ultrason
algoritma laboratuvarı geliştirdim. Kanal gecikmesi, dinamik açıklık, açı birleştirme ve zarf
çıkarma zincirini uyguladım. Kaba görüntü ızgarasındaki zarf çıkarma sorununu kanal üzerinde
analitik işleme ile ele aldım. Değişiklikleri fiziksel fantom ölçütleri, kayıtlı referanslar
ve farklı kayıtlara aktarım deneyleriyle değerlendirdim. CPU hızlandırma, açı gruplama ve
önbellek için sayısal eşdeğerlik ile zaman-bellek maliyetlerini ölçtüm. Kazançları ve olumsuz
ödünleşimleri birlikte raporladım; gerçek zamanlı cihaz ve klinik performans iddiasında
bulunmadım.”
