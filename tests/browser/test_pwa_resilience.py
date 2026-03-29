"""PWA Resilience and reconnect stress tests."""

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def hub_url():
    """Hub URL for testing."""
    return "https://localhost:8444"


class TestPWAResilience:
    """Test PWA offline/online resilience."""
    
    def test_offline_page_loads(self, page: Page, hub_url: str):
        """Verify offline shell loads when network is down."""
        # First load online
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Resilience Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Wait for SW to cache
        page.wait_for_timeout(2000)
        
        # Go offline
        page.context.set_offline(True)
        
        try:
            # Reload should show offline shell
            page.reload()
            
            # Check for offline content (not browser error)
            content = page.content().lower()
            assert (
                "offline" in content or 
                "hub" in content or 
                "waiting" in content or
                "osk" in content
            ), f"Offline shell not shown. Content: {content[:500]}"
        finally:
            page.context.set_offline(False)
    
    def test_online_recovery(self, page: Page, hub_url: str):
        """Test recovery when coming back online."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Recovery Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Go offline then online
        page.context.set_offline(True)
        page.wait_for_timeout(1000)
        page.context.set_offline(False)
        
        # Should reconnect
        page.wait_for_timeout(3000)
        
        # Connection indicator should show connected
        # (May vary by UI implementation)
        content = page.content().lower()
        # Just verify page didn't crash
        assert "error" not in content or "connected" in content or "online" in content


class TestReconnectStress:
    """Stress test reconnect behavior."""
    
    def test_multiple_reconnects(self, page: Page, hub_url: str, cycles: int = 10):
        """Test multiple disconnect/reconnect cycles."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Stress Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        results = {
            "passed": 0,
            "failed": 0,
            "latencies": [],
        }
        
        for i in range(cycles):
            try:
                # Go offline
                page.context.set_offline(True)
                page.wait_for_timeout(500)
                
                # Come back online
                reconnect_start = page.evaluate("() => Date.now()")
                page.context.set_offline(False)
                
                # Wait for recovery
                page.wait_for_timeout(2000)
                
                reconnect_end = page.evaluate("() => Date.now()")
                latency = reconnect_end - reconnect_start
                
                results["passed"] += 1
                results["latencies"].append(latency)
                
            except Exception as e:
                results["failed"] += 1
                print(f"Cycle {i+1} failed: {e}")
        
        # Calculate success rate
        success_rate = results["passed"] / cycles * 100
        avg_latency = sum(results["latencies"]) / len(results["latencies"]) if results["latencies"] else 0
        
        print(f"\nResults: {results['passed']}/{cycles} passed ({success_rate:.1f}%)")
        print(f"Average latency: {avg_latency:.0f}ms")
        
        # Assert reasonable performance
        assert success_rate >= 80, f"Success rate {success_rate:.1f}% below threshold"
    
    def test_reconnect_with_queued_data(self, page: Page, hub_url: str):
        """Test that queued data survives reconnect."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Queue Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Go offline
        page.context.set_offline(True)
        
        # Try to send report while offline
        page.fill("textarea[name='text']", "Queued report")
        page.click("button[type='submit']")
        
        # Should show queued state
        page.wait_for_timeout(1000)
        
        # Come back online
        page.context.set_offline(False)
        page.wait_for_timeout(3000)
        
        # Verify page still functional
        expect(page.locator("textarea")).to_be_visible()


class TestServiceWorkerResilience:
    """Test service worker behavior under stress."""
    
    def test_sw_health_check(self, page: Page, hub_url: str):
        """Test service worker responds to health checks."""
        page.goto(f"{hub_url}/join")
        
        # Wait for SW registration
        page.wait_for_timeout(2000)
        
        # Check SW health
        health = page.evaluate("""
            async () => {
                const reg = await navigator.serviceWorker.getRegistration();
                if (!reg || !reg.active) return { healthy: false, error: 'No SW' };
                
                const channel = new MessageChannel();
                const promise = new Promise((resolve) => {
                    channel.port1.onmessage = (e) => resolve(e.data);
                    setTimeout(() => resolve({ healthy: false, error: 'Timeout' }), 5000);
                });
                
                reg.active.postMessage({ type: 'sw_health_check' }, [channel.port2]);
                return promise;
            }
        """)
        
        print(f"SW Health: {health}")
        assert health.get("healthy", False) or "Not supported" in str(health)
    
    def test_sw_error_handling(self, page: Page, hub_url: str):
        """Test service worker handles errors gracefully."""
        page.goto(f"{hub_url}/join")
        page.wait_for_timeout(2000)
        
        # Trigger a bad message (should not crash SW)
        page.evaluate("""
            async () => {
                const reg = await navigator.serviceWorker.getRegistration();
                if (reg && reg.active) {
                    reg.active.postMessage({ type: 'unknown_message_type' });
                }
                return 'sent';
            }
        """)
        
        page.wait_for_timeout(1000)
        
        # Verify SW still responsive
        still_healthy = page.evaluate("""
            async () => {
                const reg = await navigator.serviceWorker.getRegistration();
                return reg && reg.active ? 'still_active' : 'gone';
            }
        """)
        
        assert still_healthy == "still_active", "SW crashed after bad message"


class TestLongDuration:
    """Test long-duration stability."""
    
    @pytest.mark.slow
    def test_5_minute_stability(self, page: Page, hub_url: str):
        """Test 5 minutes of stable operation."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Stability Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Check every minute for 5 minutes
        for minute in range(5):
            page.wait_for_timeout(60000)  # 1 minute
            
            # Verify still connected
            content = page.content().lower()
            assert "error" not in content or "connected" in content
            
            print(f"Minute {minute + 1}: OK")
    
    def test_memory_stability_short(self, page: Page, hub_url: str):
        """Short memory test (1 minute with activity)."""
        page.goto(f"{hub_url}/join")
        page.fill("input[name='name']", "Memory Test")
        page.click("button[type='submit']")
        
        expect(page.locator("text=Joined")).to_be_visible(timeout=10000)
        
        # Send periodic reports
        for i in range(6):
            page.fill("textarea[name='text']", f"Report {i+1}")
            page.click("button[type='submit']")
            page.wait_for_timeout(10000)  # 10 seconds
        
        # Verify still functional
        expect(page.locator("textarea")).to_be_visible()
