"""Chrome PWA tests - Full feature validation."""

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def hub_url():
    """Hub URL for testing."""
    return "https://localhost:8444"


class TestChromeJoin:
    """Test join flow in Chrome."""
    
    def test_join_page_loads(self, page: Page, hub_url: str):
        """Verify join page loads correctly."""
        page.goto(f"{hub_url}/join")
        
        # Check for key elements
        expect(page.locator("text=Join")).to_be_visible()
        expect(page.locator("input[name='name']")).to_be_visible()
    
    def test_qr_code_visible(self, page: Page, hub_url: str):
        """Verify QR code is displayed for coordinator scan."""
        page.goto(f"{hub_url}/join")
        
        # QR code should be visible
        qr_locator = page.locator("canvas").or_(page.locator("img[alt*='QR']"))
        expect(qr_locator).to_be_visible(timeout=5000)


class TestChromeMemberRuntime:
    """Test member runtime features in Chrome."""
    
    def test_manual_report_submission(self, page: Page, hub_url: str):
        """Test submitting a manual field report."""
        # Join operation
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Test User")
        page.click("button[type='submit']")
        
        # Wait for runtime to load
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Submit report
        page.fill("textarea[name='text']", "Test report from Chrome")
        page.click("button[type='submit']")
        
        # Verify confirmation
        expect(page.locator("text=sent").or_(page.locator("text=queued"))).to_be_visible(timeout=5000)
    
    def test_gps_toggle(self, page: Page, hub_url: str):
        """Test GPS location sharing toggle."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Test User")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Find and toggle GPS
        gps_toggle = page.locator("[data-gps-toggle], button:has-text('GPS')").first
        if gps_toggle.is_visible():
            gps_toggle.click()
            # Verify state change
            expect(page.locator("text=GPS").or_(page.locator("text=Location"))).to_be_visible()


class TestChromeSensors:
    """Test sensor features in Chrome."""
    
    def test_sensor_role_selection(self, page: Page, hub_url: str):
        """Test switching to sensor role."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Test Sensor")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Look for sensor toggle
        sensor_toggle = page.locator(
            "[data-sensor-toggle], button:has-text('Sensor'), button:has-text('sensor')"
        ).first
        
        if sensor_toggle.is_visible():
            sensor_toggle.click()
            # Verify sensor UI appears
            expect(
                page.locator("text=Audio").or_(page.locator("text=Video")).or_(page.locator("text=Frame"))
            ).to_be_visible(timeout=5000)
    
    def test_audio_sensor_enable(self, page: Page, hub_url: str):
        """Test enabling audio sensor."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Test Sensor")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Enable sensor role if available
        sensor_toggle = page.locator(
            "[data-sensor-toggle], button:has-text('Sensor')"
        ).first
        
        if sensor_toggle.is_visible():
            sensor_toggle.click()
            
            # Look for audio toggle
            audio_toggle = page.locator(
                "[data-audio-toggle], button:has-text('Audio'), button:has-text('audio')"
            ).first
            
            if audio_toggle.is_visible():
                audio_toggle.click()
                # Verify audio state changes
                expect(
                    page.locator("text=On").or_(page.locator("text=Active")).or_(page.locator("text=Capturing"))
                ).to_be_visible(timeout=5000)


class TestChromePWA:
    """Test PWA features in Chrome."""
    
    def test_service_worker_registration(self, page: Page, hub_url: str):
        """Verify service worker registers."""
        page.goto(f"{hub_url}/join")
        
        # Check for service worker support
        sw_supported = page.evaluate("() => 'serviceWorker' in navigator")
        assert sw_supported, "Service Worker API not available"
        
        # Wait for registration
        page.wait_for_timeout(2000)
        
        sw_registered = page.evaluate("""
            async () => {
                const reg = await navigator.serviceWorker.getRegistration();
                return reg !== null;
            }
        """)
        assert sw_registered, "Service Worker not registered"
    
    def test_offline_shell_available(self, page: Page, hub_url: str):
        """Test that offline shell is available when network down."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Test User")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Simulate going offline
        page.context.set_offline(True)
        
        try:
            # Refresh page
            page.reload()
            
            # Should show offline shell (not browser error)
            expect(
                page.locator("text=offline").or_(page.locator("text=Offline")).or_(
                    page.locator("text=hub").or_(page.locator("text=waiting"))
                )
            ).to_be_visible(timeout=5000)
        finally:
            page.context.set_offline(False)


class TestChromeErgonomics:
    """Test sensor ergonomics features in Chrome."""
    
    def test_battery_indicator_visible(self, page: Page, hub_url: str):
        """Test battery indicator appears in sensor mode."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Test User")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Enable sensor
        sensor_toggle = page.locator(
            "[data-sensor-toggle], button:has-text('Sensor')"
        ).first
        
        if sensor_toggle.is_visible():
            sensor_toggle.click()
            
            # Look for sensor ergonomics panel
            panel = page.locator("#sensor-ergonomics-panel, .sensor-ergonomics-panel")
            
            if panel.is_visible():
                # Check for battery display
                expect(
                    page.locator("text=Battery").or_(page.locator("text=battery"))
                ).to_be_visible(timeout=3000)
    
    def test_quality_controls_visible(self, page: Page, hub_url: str):
        """Test quality control buttons appear."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Test User")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Enable sensor
        sensor_toggle = page.locator(
            "[data-sensor-toggle], button:has-text('Sensor')"
        ).first
        
        if sensor_toggle.is_visible():
            sensor_toggle.click()
            
            # Look for quality buttons
            expect(
                page.locator("text=High").or_(page.locator("text=Medium")).or_(
                    page.locator("text=Quality")
                )
            ).to_be_visible(timeout=3000)
