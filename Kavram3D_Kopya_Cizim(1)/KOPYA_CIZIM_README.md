# Kavram3D — Kopya ile Çizim

Bu sürümde 3B nesneler tek bir mesh'e dönüştürülmeden ayrı nesneler olarak tutulur. Çoklu seçimle oluşturulan bir grup, sol fare sürüklemesi boyunca grup içindeki göreli konumlarını koruyarak çoğaltılır.

## Fare davranışı

- **Sol tık + sürükle:** aktif çizim fırçası.
  - Çoklu seçim varsa seçili nesnelerin tamamını, ayrı nesneler olarak kopyalar.
  - Çoklu seçim yoksa Objects panelindeki aktif cisim türünü damgalar.
  - Kopya üretilirken muhafazakâr küre tabanlı çakışma kontrolü yapılır; yeni grup mevcut nesnelerle kesişiyorsa o damga atlanır.
- **Shift + sol tık:** nesne seçimine ekle/çıkar.
- **Shift + sol tık + sürükle:** seçim kutusu; kutu içindeki nesneler seçime eklenir.
- **Ctrl + sol tık:** seçili nesne/grubun tamamını siler. Önceden seçim yoksa imleç altındaki nesneyi siler.
- **Ctrl + sol tık + sürükle:** silme fırçası; sürükleme boyunca imleç altındaki nesneler kaldırılır.
- **Orta tuş:** görünüm döndürme.
- **Shift + orta tuş:** kaydırma.
- **Ctrl + orta tuş:** yakınlaştırma/uzaklaştırma.

## Kopya grupları

Grup kopyası meshleri birleştirmez. Her yeni parça ayrı bir obje olarak kalır ve şunlar korunur:

- mesh türü
- göreli konum
- dönüş
- ölçek
- renk
- hareket modu, eksen ve hız

Animasyonlu bir nesne grubunun kopyası da ayrı nesneler halinde oluşturulur.

## İçe aktarma

GLB/glTF düğümleri ayrı Kavram nesnelerine ayrılır; böylece Blender'dan dışa aktarılan atom benzeri çok parçalı yapı tekrar tek nesneye indirgenmez.

`.blend`, FBX, OBJ, STL, PLY, DAE ve 3DS için sistemde `blender` veya `blender-launcher` bulunuyorsa dosya önce headless Blender ile GLB'ye dönüştürülür.

## Derleme

```bash
cd Kavram3D_Kopya_Cizim
chmod +x build.sh
./build.sh
```

Bu komut C motorlarını derler ve Python kaynaklarının sözdizimini kontrol eder.

## Çalıştırma

Mevcut sanal ortam kullanılıyorsa:

```bash
cd Kavram3D_Kopya_Cizim
source venv/bin/activate
QT_QPA_PLATFORM=xcb python3 Kavram.py
```

Yeni bir ortam gerekiyorsa `requirements.txt` içindeki PyQt5 ve PyOpenGL bağımlılıkları kurulmalıdır.

## Test sonucu

Motor seviyesinde grup kopyalama, kutu seçimi, çakışma reddi ve son nesnenin silinebilmesi doğrulandı. Grafik arayüzünün gerçek açılışı, bu paketleme ortamında PyQt5 kurulu olmadığı için burada çalıştırılmadı; kaynak ve C motoru derleme testleri temizdir.
