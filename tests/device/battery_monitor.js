/**
 * Battery Monitoring Framework for Real-Device Validation
 * 
 * Usage:
 *   1. Include this script in member.html for testing
 *   2. Call BatteryMonitor.start() to begin logging
 *   3. Call BatteryMonitor.stop() to get report
 *   4. Export report for analysis
 */

(function() {
  'use strict';

  const BatteryMonitor = {
    // Configuration
    config: {
      logInterval: 5000,        // Log every 5 seconds
      reportInterval: 60000,    // Generate report every minute
      storageKey: 'osk_battery_log',
      maxEntries: 1000,         // Prevent unbounded growth
    },

    // State
    isRunning: false,
    battery: null,
    startTime: null,
    logTimer: null,
    reportTimer: null,
    sessionId: null,

    // Initialize
    async init() {
      if (!('getBattery' in navigator)) {
        console.warn('[BatteryMonitor] Battery API not supported');
        return false;
      }

      try {
        this.battery = await navigator.getBattery();
        this.sessionId = `session-${Date.now()}`;
        console.log('[BatteryMonitor] Initialized');
        return true;
      } catch (error) {
        console.error('[BatteryMonitor] Init failed:', error);
        return false;
      }
    },

    // Start monitoring
    async start() {
      if (this.isRunning) {
        console.log('[BatteryMonitor] Already running');
        return;
      }

      if (!this.battery) {
        const initialized = await this.init();
        if (!initialized) return;
      }

      this.isRunning = true;
      this.startTime = Date.now();

      // Log initial state
      this.logEntry('start', this.getBatteryState());

      // Set up interval logging
      this.logTimer = setInterval(() => {
        this.logEntry('sample', this.getBatteryState());
      }, this.config.logInterval);

      // Set up report generation
      this.reportTimer = setInterval(() => {
        this.generateSnapshot();
      }, this.config.reportInterval);

      // Listen for battery events
      this.battery.addEventListener('levelchange', () => {
        this.logEntry('levelchange', this.getBatteryState());
      });

      this.battery.addEventListener('chargingchange', () => {
        this.logEntry('chargingchange', this.getBatteryState());
      });

      this.battery.addEventListener('chargingtimechange', () => {
        this.logEntry('chargingtimechange', this.getBatteryState());
      });

      this.battery.addEventListener('dischargingtimechange', () => {
        this.logEntry('dischargingtimechange', this.getBatteryState());
      });

      console.log('[BatteryMonitor] Started');
    },

    // Stop monitoring
    stop() {
      if (!this.isRunning) {
        console.log('[BatteryMonitor] Not running');
        return null;
      }

      this.isRunning = false;

      if (this.logTimer) {
        clearInterval(this.logTimer);
        this.logTimer = null;
      }

      if (this.reportTimer) {
        clearInterval(this.reportTimer);
        this.reportTimer = null;
      }

      this.logEntry('stop', this.getBatteryState());

      const report = this.generateReport();
      console.log('[BatteryMonitor] Stopped');
      return report;
    },

    // Get current battery state
    getBatteryState() {
      if (!this.battery) return null;

      return {
        level: this.battery.level,
        charging: this.battery.charging,
        chargingTime: this.battery.chargingTime,
        dischargingTime: this.battery.dischargingTime,
        timestamp: Date.now(),
      };
    },

    // Log an entry
    logEntry(event, state) {
      const entry = {
        sessionId: this.sessionId,
        event,
        state,
        elapsed: this.startTime ? Date.now() - this.startTime : 0,
      };

      // Get existing logs
      const logs = this.getStoredLogs();
      
      // Add new entry
      logs.push(entry);

      // Trim to max entries
      while (logs.length > this.config.maxEntries) {
        logs.shift();
      }

      // Store back
      this.storeLogs(logs);
    },

    // Get stored logs from localStorage
    getStoredLogs() {
      try {
        const stored = localStorage.getItem(this.config.storageKey);
        return stored ? JSON.parse(stored) : [];
      } catch (error) {
        console.error('[BatteryMonitor] Failed to read logs:', error);
        return [];
      }
    },

    // Store logs to localStorage
    storeLogs(logs) {
      try {
        localStorage.setItem(this.config.storageKey, JSON.stringify(logs));
      } catch (error) {
        console.error('[BatteryMonitor] Failed to store logs:', error);
        // If storage is full, clear old logs
        if (error.name === 'QuotaExceededError') {
          this.clearLogs();
        }
      }
    },

    // Clear all logs
    clearLogs() {
      localStorage.removeItem(this.config.storageKey);
      console.log('[BatteryMonitor] Logs cleared');
    },

    // Generate a snapshot report
    generateSnapshot() {
      const logs = this.getStoredLogs();
      const report = this.analyzeLogs(logs);
      
      console.log('[BatteryMonitor] Snapshot:', report);
      
      // Dispatch event for UI
      window.dispatchEvent(new CustomEvent('osk:battery-snapshot', { 
        detail: report 
      }));

      return report;
    },

    // Generate final report
    generateReport() {
      const logs = this.getStoredLogs();
      const report = this.analyzeLogs(logs);
      
      // Add metadata
      report.metadata = {
        sessionId: this.sessionId,
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        startTime: this.startTime,
        endTime: Date.now(),
        duration: this.startTime ? Date.now() - this.startTime : 0,
      };

      // Store report
      this.storeReport(report);

      return report;
    },

    // Analyze logs
    analyzeLogs(logs) {
      if (logs.length === 0) {
        return { error: 'No logs available' };
      }

      // Filter to current session
      const sessionLogs = logs.filter(l => l.sessionId === this.sessionId);
      
      if (sessionLogs.length === 0) {
        return { error: 'No logs for current session' };
      }

      const startLog = sessionLogs.find(l => l.event === 'start');
      const stopLog = sessionLogs.find(l => l.event === 'stop');
      const samples = sessionLogs.filter(l => l.event === 'sample');

      if (!startLog || samples.length === 0) {
        return { error: 'Insufficient data' };
      }

      const startLevel = startLog.state.level;
      const endLevel = stopLog ? stopLog.state.level : samples[samples.length - 1].state.level;
      const levelChange = endLevel - startLevel;

      // Calculate drain rate (% per hour)
      const durationHours = (samples[samples.length - 1].elapsed - samples[0].elapsed) / (1000 * 60 * 60);
      const drainRate = durationHours > 0 ? (levelChange / durationHours) : 0;

      return {
        sessionId: this.sessionId,
        sampleCount: samples.length,
        duration: samples[samples.length - 1].elapsed - samples[0].elapsed,
        startLevel,
        endLevel,
        levelChange,
        drainRate: Math.abs(drainRate),
        drainPercentPerHour: Math.abs(drainRate * 100).toFixed(2),
        estimatedHoursRemaining: drainRate !== 0 ? Math.abs(endLevel / drainRate).toFixed(1) : 'N/A',
        wasCharging: startLog.state.charging,
        samples: samples.map(s => ({
          elapsed: s.elapsed,
          level: s.state.level,
          charging: s.state.charging,
        })),
      };
    },

    // Store report
    storeReport(report) {
      const key = `${this.config.storageKey}-report-${this.sessionId}`;
      try {
        localStorage.setItem(key, JSON.stringify(report));
      } catch (error) {
        console.error('[BatteryMonitor] Failed to store report:', error);
      }
    },

    // Get all stored reports
    getAllReports() {
      const reports = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.startsWith(`${this.config.storageKey}-report-`)) {
          try {
            reports.push(JSON.parse(localStorage.getItem(key)));
          } catch (error) {
            console.error('[BatteryMonitor] Failed to parse report:', error);
          }
        }
      }
      return reports.sort((a, b) => b.metadata.startTime - a.metadata.startTime);
    },

    // Export data as JSON
    exportData() {
      const logs = this.getStoredLogs();
      const reports = this.getAllReports();
      return {
        logs,
        reports,
        exportedAt: new Date().toISOString(),
      };
    },

    // Get sensor state (if available)
    getSensorState() {
      // This would integrate with member.js to get sensor status
      // For now, return a placeholder
      return {
        audioCapturing: window.OskAudioCapture?.isCapturing?.() || false,
        frameCapturing: window.OskFrameSampler?.isSampling?.() || false,
        pendingUploads: window.OskMemberOutbox?.snapshot?.().pendingCount || 0,
      };
    },
  };

  // Expose globally
  window.BatteryMonitor = BatteryMonitor;

  // Auto-init if requested via URL param
  if (new URLSearchParams(window.location.search).has('battery-monitor')) {
    window.addEventListener('load', () => {
      BatteryMonitor.init();
    });
  }
})();
