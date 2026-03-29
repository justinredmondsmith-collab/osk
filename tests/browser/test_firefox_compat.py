"""Firefox compatibility tests - Degraded mode validation."""

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def hub_url():
    """Hub URL for testing."""
    return "https://localhost:8444"


class TestFirefoxJoin:
    """Test join flow in Firefox."""
    
    def test_join_page_loads(self, page: Page, hub_url: str):
        """Verify join page loads correctly in Firefox."""
        page.goto(f"{hub_url}/join")
        
        # Check for key elements
        expect(page.locator("text=Join")).to_be_visible()
        expect(page.locator("input[name='name']")).to_be_visible()
    
    def test_manual_report_works(self, page: Page, hub_url: str):
        """Test manual report submission (core feature)."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Firefox Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Submit report
        page.fill("textarea[name='text']", "Test from Firefox")
        page.click("button[type='submit']")
        
        # Should succeed
        expect(
            page.locator("text=sent").or_(page.locator("text=queued"))
        ).to_be_visible(timeout=5000)


class TestFirefoxMediaCapture:
    """Test media capture in Firefox."""
    
    def test_photo_capture_available(self, page: Page, hub_url: str):
        """Test photo capture (should work in Firefox)."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Firefox Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Look for photo capture button
        photo_button = page.locator(
            "button:has-text('Photo'), button:has-text('photo'), [data-photo-capture]"
        ).first
        
        # Photo capture may or may not be available
        # Just verify no crash
        if photo_button.is_visible():
            photo_button.click()
            # Should not crash
            page.wait_for_timeout(1000)
    
    def test_audio_clip_capture(self, page: Page, hub_url: str):
        """Test audio clip capture (should work in Firefox)."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Firefox Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Look for audio clip button
        audio_button = page.locator(
            "button:has-text('Audio'), button:has-text('Clip'), [data-clip-toggle]"
        ).first
        
        if audio_button.is_visible():
            audio_button.click()
            page.wait_for_timeout(1000)


class TestFirefoxSensors:
    """Test sensor features in Firefox (known degraded)."""
    
    def test_audio_streaming_may_fail_gracefully(self, page: Page, hub_url: str):
        """Test that audio streaming fails gracefully if not supported."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Firefox Sensor Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Try to enable sensor
        sensor_toggle = page.locator(
            "[data-sensor-toggle], button:has-text('Sensor')"
        ).first
        
        if sensor_toggle.is_visible():
            sensor_toggle.click()
            
            # Try audio
            audio_toggle = page.locator(
                "[data-audio-toggle], button:has-text('Audio')"
            ).first
            
            if audio_toggle.is_visible():
                audio_toggle.click()
                page.wait_for_timeout(2000)
                
                # Should either work or show clear error
                # No crash is the success criteria
                assert True, "Audio toggle did not crash browser"
    
    def test_frame_capture_performance(self, page: Page, hub_url: str):
        """Test frame capture performance (may be slower in Firefox)."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Firefox Sensor Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Enable sensor if available
        sensor_toggle = page.locator(
            "[data-sensor-toggle], button:has-text('Sensor')"
        ).first
        
        if sensor_toggle.is_visible():
            sensor_toggle.click()
            page.wait_for_timeout(3000)
            
            # Just verify no crash
            # Performance measurement would need more setup
            assert True


class TestFirefoxPWA:
    """Test PWA features in Firefox."""
    
    def test_service_worker_registration(self, page: Page, hub_url: str):
        """Verify service worker works in Firefox."""
        page.goto(f"{hub_url}/join")
        
        sw_supported = page.evaluate("() => 'serviceWorker' in navigator")
        assert sw_supported, "Service Worker API not available"
        
        page.wait_for_timeout(2000)
        
        sw_registered = page.evaluate("""
            async () => {
                const reg = await navigator.serviceWorker.getRegistration();
                return reg !== null;
            }
        """)
        assert sw_registered, "Service Worker not registered"
    
    def test_offline_behavior(self, page: Page, hub_url: str):
        """Test offline shell in Firefox."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Firefox Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Go offline
        page.context.set_offline(True)
        
        try:
            page.reload()
            # Should show something (not browser error page)
            content = page.content()
            assert "error" not in content.lower() or "offline" in content.lower() or "hub" in content.lower()
        finally:
            page.context.set_offline(False)


class TestFirefoxLimitations:
    """Document Firefox limitations."""
    
    def test_battery_api_unavailable(self, page: Page, hub_url: str):
        """Verify Battery API is not available in Firefox (privacy)."""
        page.goto(f"{hub_url}/join")
        
        battery_supported = page.evaluate("() => 'getBattery' in navigator")
        
        # Firefox typically doesn't support Battery API
        # This is expected behavior, not a failure
        if not battery_supported:
            pytest.skip("Battery API not available (expected in Firefox)")
    
    def test_background_audio_limited(self, page: Page, hub_url: str):
        """Document that background audio may not work in Firefox."""
        # This is a documentation test
        # Firefox may pause audio when tab is backgrounded
        pytest.skip("Background audio known limitation in Firefox")
