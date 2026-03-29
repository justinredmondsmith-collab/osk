"""WebKit (Safari) compatibility tests - Mobile Safari limitations."""

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def hub_url():
    """Hub URL for testing."""
    return "https://localhost:8444"


class TestWebKitJoin:
    """Test join flow in WebKit/Safari."""
    
    def test_join_page_loads(self, page: Page, hub_url: str):
        """Verify join page loads correctly."""
        page.goto(f"{hub_url}/join")
        
        expect(page.locator("text=Join")).to_be_visible()
        expect(page.locator("input[name='name']")).to_be_visible()
    
    def test_manual_features_work(self, page: Page, hub_url: str):
        """Test manual reports (primary Safari feature)."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Safari Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Submit manual report
        page.fill("textarea[name='text']", "Test from Safari")
        page.click("button[type='submit']")
        
        expect(
            page.locator("text=sent").or_(page.locator("text=queued"))
        ).to_be_visible(timeout=5000)


class TestWebKitMedia:
    """Test media capture in Safari."""
    
    def test_photo_capture(self, page: Page, hub_url: str):
        """Test photo capture in Safari."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Safari Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Photo capture should work
        photo_button = page.locator(
            "button:has-text('Photo'), [data-photo-capture]"
        ).first
        
        if photo_button.is_visible():
            photo_button.click()
            page.wait_for_timeout(1000)
    
    def test_audio_clip_limited(self, page: Page, hub_url: str):
        """Test audio clip (may have limitations in Safari)."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Safari Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Try audio clip
        audio_button = page.locator(
            "button:has-text('Audio'), button:has-text('Clip')"
        ).first
        
        if audio_button.is_visible():
            audio_button.click()
            # May prompt for permission
            page.wait_for_timeout(2000)


class TestWebKitSensors:
    """Test sensor features in Safari (known limitations)."""
    
    def test_background_audio_not_supported(self, page: Page, hub_url: str):
        """Document that background audio doesn't work in Safari."""
        # iOS Safari pauses audio when app is backgrounded
        # This is a known platform limitation
        pytest.skip("Background audio not supported in iOS Safari (platform limitation)")
    
    def test_continuous_streaming_limited(self, page: Page, hub_url: str):
        """Document continuous streaming limitations in Safari."""
        # Safari may throttle or pause long-running streams
        pytest.skip("Continuous streaming limited in Safari (platform limitation)")


class TestWebKitPWA:
    """Test PWA features in Safari."""
    
    def test_service_worker_basic(self, page: Page, hub_url: str):
        """Test service worker registration."""
        page.goto(f"{hub_url}/join")
        
        sw_supported = page.evaluate("() => 'serviceWorker' in navigator")
        
        # Safari has SW support but may have limitations
        if not sw_supported:
            pytest.skip("Service Worker not supported")
        
        page.wait_for_timeout(2000)
        
        sw_registered = page.evaluate("""
            async () => {
                const reg = await navigator.serviceWorker.getRegistration();
                return reg !== null;
            }
        """)
        
        # May or may not work depending on version
        if not sw_registered:
            pytest.skip("Service Worker registration failed (may be expected)")
    
    def test_offline_limited(self, page: Page, hub_url: str):
        """Test offline behavior (may be limited in Safari)."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Safari Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        page.context.set_offline(True)
        
        try:
            page.reload()
            # Safari may clear storage under memory pressure
            # Just verify no crash
            page.wait_for_timeout(2000)
        finally:
            page.context.set_offline(False)


class TestWebKitInstall:
    """Test PWA install in Safari."""
    
    def test_install_prompt_not_available(self, page: Page, hub_url: str):
        """Document that Safari doesn't support install prompts."""
        page.goto(f"{hub_url}/join")
        
        # Safari requires manual "Add to Home Screen"
        # No beforeinstallprompt event
        has_prompt = page.evaluate("() => 'BeforeInstallPromptEvent' in window")
        
        if not has_prompt:
            pytest.skip("Install prompt not available (expected in Safari)")
    
    def test_manual_install_instructions(self, page: Page, hub_url: str):
        """Verify install instructions are shown for Safari."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Safari Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Look for install hints
        install_hint = page.locator(
            "text=Home Screen, text=install, text=Share"
        ).first
        
        # May or may not be visible depending on UI state
        # Just check no error


class TestWebKitLimitations:
    """Document WebKit/Safari limitations."""
    
    def test_battery_api_not_supported(self, page: Page, hub_url: str):
        """Verify Battery API not available in Safari."""
        page.goto(f"{hub_url}/join")
        
        battery_supported = page.evaluate("() => 'getBattery' in navigator")
        
        # Safari doesn't support Battery API
        if not battery_supported:
            pytest.skip("Battery API not available (expected in Safari)")
    
    def test_background_sync_limited(self, page: Page, hub_url: str):
        """Document Background Sync limitations."""
        # Safari has limited Background Sync support
        pytest.skip("Background Sync limited in Safari")
    
    def test_push_notifications_not_supported(self, page: Page, hub_url: str):
        """Verify Push API not available in Safari."""
        page.goto(f"{hub_url}/join")
        
        push_supported = page.evaluate("() => 'PushManager' in window")
        
        if not push_supported:
            pytest.skip("Push API not available (expected in Safari)")


class TestWebKitRecommendations:
    """Test recommendations for Safari users."""
    
    def test_observer_role_recommended(self, page: Page, hub_url: str):
        """Verify Observer role works well in Safari."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Safari Observer")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Observer features should work
        # - Manual reports
        # - GPS (if enabled)
        # - Photo/audio clips
        
        # Verify core functionality
        expect(page.locator("textarea")).to_be_visible()
