# Flutter App Integration Guide

## Mô tả

Flutter app sẽ gửi signal tới Backend khi:
1. **App vừa được mở** → Gọi endpoint `/drawer/app-opened`
2. **App bị đóng/thoát** → Gọi endpoint `/drawer/app-closed`

Backend sẽ:
- Khi nhận signal mở → **Tạm dừng điều khiển tự động** (AI vẫn hoạt động)
- Khi nhận signal đóng → **Tiếp tục điều khiển tự động**

---

## 📡 API Endpoints

### 1. App Opened - Pause Drawer Control

**Endpoint:** `POST /api/v1/drawer/app-opened`

**Khi gọi:**
- Ngay khi `initState()` hoặc `onForeground()` (app vừa open)

**Request:**
```http
POST http://YOUR_SERVER_IP:8000/api/v1/drawer/app-opened
Content-Type: application/json
```

**Response (Success):**
```json
{
  "success": true,
  "paused": true,
  "pause_until_time": 1712973600.5,
  "message": "Drawer control paused, AI still active for notifications"
}
```

**Ý nghĩa:**
- ✅ Drawer control bị pause (không tự mở/đóng)
- ✅ AI vẫn hoạt động:
  - Vẫn phát hiện người ra/vào
  - Vẫn gửi thông báo (people_count, has_di_xa_co)
- ⏰ Sẽ auto-resume sau 60s nếu app không interactive

---

### 2. App Closed - Resume Drawer Control

**Endpoint:** `POST /api/v1/drawer/app-closed`

**Khi gọi:**
- Khi user tắt app (onDestroy, onBackground)
- Khi user swipe app khỏi recent apps
- Khi user logout
- làm thêm một nút bấm trên màn hình để khi user bấm tắt nút này nghĩa là app đã đóng gửi signal tới Backend như những cái trên để BE mở lại phần điều khiển tự động

**Request:**
```http
POST http://YOUR_SERVER_IP:8000/api/v1/drawer/app-closed
Content-Type: application/json
```

**Response (Success):**
```json
{
  "success": true,
  "resumed": true,
  "paused": false,
  "message": "Drawer control resumed"
}
```

**Ý nghĩa:**
- ✅ Drawer control được bật lại
- ✅ AI có thể gửi lệnh mở/đóng tủ kéo tự động

---

## 🚀 Flutter Implementation Example

### Single Page (BLoC Pattern)

```dart
import 'package:http/http.dart' as http;

class DrawerBloc extends Bloc<DrawerEvent, DrawerState> {
  final String serverUrl;
  
  @override
  Stream<DrawerState> mapEventToState(DrawerEvent event) async* {
    if (event is AppOpenedEvent) {
      yield* _onAppOpened();
    } else if (event is AppClosedEvent) {
      yield* _onAppClosed();
    }
  }
  
  Stream<DrawerState> _onAppOpened() async* {
    try {
      final response = await http.post(
        Uri.parse('$serverUrl/api/v1/drawer/app-opened'),
      ).timeout(Duration(seconds: 5));
      
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        yield DrawerControlPaused(
          pauseUntilTime: data['pause_until_time'],
        );
      }
    } catch (e) {
      yield DrawerError(error: e.toString());
    }
  }
  
  Stream<DrawerState> _onAppClosed() async* {
    try {
      final response = await http.post(
        Uri.parse('$serverUrl/api/v1/drawer/app-closed'),
      ).timeout(Duration(seconds: 5));
      
      if (response.statusCode == 200) {
        yield DrawerControlResumed();
      }
    } catch (e) {
      yield DrawerError(error: e.toString());
    }
  }
}
```

### App Lifecycle Management

```dart
class MainApp extends StatefulWidget {
  @override
  State<MainApp> createState() => _MainAppState();
}

class _MainAppState extends State<MainApp> with WidgetsBindingObserver {
  late DrawerBloc _drawerBloc;
  
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _drawerBloc = DrawerBloc(serverUrl: 'http://192.168.1.100:8000');
    
    // App vừa open → signal app opened
    Future.delayed(Duration(milliseconds: 500), () {
      _drawerBloc.add(AppOpenedEvent());
    });
  }
  
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.paused:
      case AppLifecycleState.detached:
        // App bị tắt/ẩn → signal app closed
        _drawerBloc.add(AppClosedEvent());
        break;
      case AppLifecycleState.resumed:
        // App quay lại foreground → signal app opened
        _drawerBloc.add(AppOpenedEvent());
        break;
      default:
        break;
    }
  }
  
  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _drawerBloc.close();
    super.dispose();
  }
  
  @override
  Widget build(BuildContext context) {
    return BlocProvider.value(
      value: _drawerBloc,
      child: MaterialApp(
        home: HomeScreen(),
      ),
    );
  }
}
```

---

## 🔄 Flow Diagram

```
App Opens                    App Closes/Exits
    ↓                               ↑
    └──→ POST /drawer/app-opened    │
         │                          │
         ├→ pause_ai_detection=true │
         ├→ AI continues            │
         └→ drawer commands blocked ─┤
                                    │
                        POST /drawer/app-closed
                        │
                        ├→ pause_ai_detection=false
                        └→ drawer can auto-control
```

---

## ⏰ Timing Notes

1. **App Open Signal (60s pause)**
   - Gọi `/app-opened` → drawer control bị pause 60s
   - Nếu app không interactive, auto-resume sau 60s
   - Nếu user vẫn dùng app, gửi lại `/app-opened` để reset timer
   - Hoặc: call `/app-closed` khi user logout

2. **App Close Signal (immediate resume)**
   - Gọi `/app-closed` → drawer control tiếp tục ngay lập tức
   - AI có thể gửi lệnh mở/đóng tủ kéo tự động

3. **Network Unreliable**
   - Nếu POST thất bại, drawer control sẽ auto-resume sau 60s
   - Logic an toàn: không block vô hạn

---

## 📋 Checklist

- [ ] Import `package:http/http.dart`
- [ ] Create DrawerBloc or Service class
- [ ] Add WidgetsBindingObserver to track app lifecycle
- [ ] Call `/app-opened` when app starts (initState or onForeground)
- [ ] Call `/app-closed` when app closes (onPaused, onDetached, or logout)
- [ ] Handle network errors gracefully
- [ ] Test with Backend logs: `docker-compose logs api`

---

## 🐛 Debugging

### Check Backend Logs

```bash
# Watch backend logs
docker-compose logs -f api

# You should see:
# [Flutter App Opened] Drawer control paused until 1712973660.5
# [Flutter App Closed] Drawer control resumed
```

### Test Endpoints Manually (curl)

```bash
# Test app opened
curl -X POST http://localhost:8000/api/v1/drawer/app-opened
# Expected: {"success": true, "paused": true, ...}

# Test app closed
curl -X POST http://localhost:8000/api/v1/drawer/app-closed
# Expected: {"success": true, "resumed": true, ...}
```

### Check Drawer State

```bash
# GET current state
curl http://localhost:8000/api/v1/drawer/status
# Check "ai_paused" field
```
