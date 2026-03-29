/**
 * Sensor Ergonomics Module - Battery-aware sensor controls
 * 
 * Features:
 * - Battery cost estimation and display
 * - Stream health monitoring (audio/video quality)
 * - Adaptive quality policies
 * - User-visible controls for sensor settings
 */

(function() {
  'use strict';

  const SensorErgonomics = {
    // Configuration
    config: {
      // Battery thresholds for adaptive policies
      battery: {
        critical: 0.15,   // 15% - stop sensors
        low: 0.30,        // 30% - reduce quality
        medium: 0.50,     // 50% - normal operation
      },
      // Quality levels
      quality: {
        high: { audioBitrate: 32000, frameQuality: 0.68, fps: 2 },
        medium: { audioBitrate: 24000, frameQuality: 0.50, fps: 1 },
        low: { audioBitrate: 16000, frameQuality: 0.35, fps: 0.5 },
        minimal: { audioBitrate: 8000, frameQuality: 0.25, fps: 0.25 },
      },
      // Health check intervals
      healthCheckInterval: 5000,
      batteryCheckInterval: 10000,
    },

    // State
    state: {
      battery: null,
      currentQuality: 'high',
      streamHealth: {
        audio: { status: 'unknown', droppedChunks: 0, lastChunkAt: null },
        video: { status: 'unknown', droppedFrames: 0, lastFrameAt: null },
      },
      isRunning: false,
      healthTimer: null,
      batteryTimer: null,
      stats: {
        startTime: null,
        totalAudioChunks: 0,
        totalFrames: 0,
        estimatedBatteryCost: 0,
      },
    },

    // UI Elements (populated on init)
    ui: {},

    /**
     * Initialize the sensor ergonomics module
     */
    async init() {
      console.log('[SensorErgonomics] Initializing...');
      
      // Check for Battery API
      if ('getBattery' in navigator) {
        try {
          this.state.battery = await navigator.getBattery();
          this.setupBatteryListeners();
          console.log('[SensorErgonomics] Battery API available');
        } catch (error) {
          console.warn('[SensorErgonomics] Battery API failed:', error);
        }
      }

      // Create UI
      this.createUI();
      
      // Start monitoring if sensors active
      if (this.isSensorActive()) {
        this.start();
      }

      console.log('[SensorErgonomics] Initialized');
      return true;
    },

    /**
     * Set up battery event listeners
     */
    setupBatteryListeners() {
      if (!this.state.battery) return;

      this.state.battery.addEventListener('levelchange', () => {
        this.handleBatteryChange();
      });

      this.state.battery.addEventListener('chargingchange', () => {
        this.handleBatteryChange();
      });
    },

    /**
     * Handle battery level or charging state change
     */
    handleBatteryChange() {
      const level = this.state.battery.level;
      const charging = this.state.battery.charging;
      
      console.log(`[SensorErgonomics] Battery: ${Math.round(level * 100)}%${charging ? ' (charging)' : ''}`);
      
      this.updateBatteryDisplay();
      
      // Apply adaptive policy if not charging
      if (!charging && this.isSensorActive()) {
        this.applyAdaptivePolicy();
      }
    },

    /**
     * Apply adaptive quality policy based on battery
     */
    applyAdaptivePolicy() {
      const level = this.state.battery?.level ?? 1.0;
      let targetQuality = 'high';
      
      if (level <= this.config.battery.critical) {
        targetQuality = 'minimal';
        this.showWarning('Battery critical - sensors at minimum quality');
      } else if (level <= this.config.battery.low) {
        targetQuality = 'low';
        this.showNotification('Battery low - reducing sensor quality');
      } else if (level <= this.config.battery.medium) {
        targetQuality = 'medium';
      }

      if (targetQuality !== this.state.currentQuality) {
        this.setQuality(targetQuality);
      }
    },

    /**
     * Set sensor quality level
     */
    setQuality(level) {
      if (!this.config.quality[level]) {
        console.error(`[SensorErgonomics] Invalid quality level: ${level}`);
        return;
      }

      this.state.currentQuality = level;
      const settings = this.config.quality[level];
      
      // Apply to global config (if available)
      if (window.sensorConfig) {
        window.sensorConfig.frameJpegQuality = settings.frameQuality;
        window.sensorConfig.frameSamplingFps = settings.fps;
        // Audio bitrate would need to be passed to audio capture
      }

      console.log(`[SensorErgonomics] Quality set to ${level}:`, settings);
      this.updateQualityDisplay();
      
      // Dispatch event for other components
      window.dispatchEvent(new CustomEvent('osk:sensor-quality-change', {
        detail: { level, settings }
      }));
    },

    /**
     * Start monitoring
     */
    start() {
      if (this.state.isRunning) return;
      
      this.state.isRunning = true;
      this.state.stats.startTime = Date.now();
      
      // Start health checks
      this.state.healthTimer = setInterval(() => {
        this.checkStreamHealth();
      }, this.config.healthCheckInterval);

      // Start battery monitoring
      if (this.state.battery) {
        this.state.batteryTimer = setInterval(() => {
          this.updateBatteryEstimate();
        }, this.config.batteryCheckInterval);
      }

      this.updateUI();
      console.log('[SensorErgonomics] Started monitoring');
    },

    /**
     * Stop monitoring
     */
    stop() {
      if (!this.state.isRunning) return;
      
      this.state.isRunning = false;
      
      if (this.state.healthTimer) {
        clearInterval(this.state.healthTimer);
        this.state.healthTimer = null;
      }

      if (this.state.batteryTimer) {
        clearInterval(this.state.batteryTimer);
        this.state.batteryTimer = null;
      }

      console.log('[SensorErgonomics] Stopped monitoring');
    },

    /**
     * Check stream health
     */
    checkStreamHealth() {
      // Check audio health
      const audioStatus = this.checkAudioHealth();
      this.state.streamHealth.audio = audioStatus;

      // Check video health
      const videoStatus = this.checkVideoHealth();
      this.state.streamHealth.video = videoStatus;

      this.updateHealthDisplay();
    },

    /**
     * Check audio stream health
     */
    checkAudioHealth() {
      // This would integrate with audio-capture.js
      // For now, return placeholder
      const lastChunk = this.state.streamHealth.audio.lastChunkAt;
      const now = Date.now();
      
      let status = 'healthy';
      if (lastChunk && (now - lastChunk) > 10000) {
        status = 'stalled';
      }

      return {
        status,
        droppedChunks: this.state.streamHealth.audio.droppedChunks,
        lastChunkAt: lastChunk,
      };
    },

    /**
     * Check video stream health
     */
    checkVideoHealth() {
      // This would integrate with frame-sampler.js
      const lastFrame = this.state.streamHealth.video.lastFrameAt;
      const now = Date.now();
      
      let status = 'healthy';
      if (lastFrame && (now - lastFrame) > 5000) {
        status = 'stalled';
      }

      return {
        status,
        droppedFrames: this.state.streamHealth.video.droppedFrames,
        lastFrameAt: lastFrame,
      };
    },

    /**
     * Update battery cost estimate
     */
    updateBatteryEstimate() {
      if (!this.state.battery || !this.state.stats.startTime) return;

      const duration = (Date.now() - this.state.stats.startTime) / (1000 * 60 * 60); // hours
      const levelChange = this.state.battery.level - (this.state.battery.levelAtStart || this.state.battery.level);
      
      if (duration > 0) {
        const drainRate = Math.abs(levelChange) / duration; // % per hour
        this.state.stats.estimatedBatteryCost = drainRate;
      }

      this.updateBatteryDisplay();
    },

    /**
     * Record audio chunk sent
     */
    recordAudioChunk() {
      this.state.stats.totalAudioChunks++;
      this.state.streamHealth.audio.lastChunkAt = Date.now();
    },

    /**
     * Record frame sent
     */
    recordFrame() {
      this.state.stats.totalFrames++;
      this.state.streamHealth.video.lastFrameAt = Date.now();
    },

    /**
     * Record dropped audio chunk
     */
    recordDroppedAudio() {
      this.state.streamHealth.audio.droppedChunks++;
    },

    /**
     * Record dropped frame
     */
    recordDroppedFrame() {
      this.state.streamHealth.video.droppedFrames++;
    },

    /**
     * Check if sensors are active
     */
    isSensorActive() {
      // Check if audio or video capture is running
      return !!(window.OskAudioCapture?.isCapturing?.() || 
                window.OskFrameSampler?.isSampling?.());
    },

    /**
     * Create UI elements
     */
    createUI() {
      // Only create if not already present
      if (document.getElementById('sensor-ergonomics-panel')) return;

      const panel = document.createElement('div');
      panel.id = 'sensor-ergonomics-panel';
      panel.className = 'sensor-ergonomics-panel';
      panel.innerHTML = `
        <div class="ergo-header">
          <span class="ergo-title">📊 Sensor Status</span>
          <button class="ergo-toggle" onclick="SensorErgonomics.togglePanel()">−</button>
        </div>
        <div class="ergo-content">
          <div class="ergo-section">
            <div class="ergo-label">Battery Impact</div>
            <div class="ergo-battery-display">
              <span id="ergo-battery-level">--%</span>
              <div class="ergo-battery-bar">
                <div id="ergo-battery-fill" class="ergo-battery-fill" style="width: 0%"></div>
              </div>
              <span id="ergo-battery-drain">--%/hr</span>
            </div>
            <div id="ergo-battery-warning" class="ergo-warning" style="display: none;"></div>
          </div>
          
          <div class="ergo-section">
            <div class="ergo-label">Stream Health</div>
            <div class="ergo-health-grid">
              <div class="ergo-health-item">
                <span class="ergo-health-indicator" id="ergo-audio-indicator">●</span>
                <span>Audio</span>
                <span id="ergo-audio-status">--</span>
              </div>
              <div class="ergo-health-item">
                <span class="ergo-health-indicator" id="ergo-video-indicator">●</span>
                <span>Video</span>
                <span id="ergo-video-status">--</span>
              </div>
            </div>
          </div>
          
          <div class="ergo-section">
            <div class="ergo-label">Quality</div>
            <div class="ergo-quality-buttons">
              <button class="ergo-quality-btn" data-quality="high" onclick="SensorErgonomics.setQuality('high')">High</button>
              <button class="ergo-quality-btn" data-quality="medium" onclick="SensorErgonomics.setQuality('medium')">Med</button>
              <button class="ergo-quality-btn" data-quality="low" onclick="SensorErgonomics.setQuality('low')">Low</button>
              <button class="ergo-quality-btn" data-quality="minimal" onclick="SensorErgonomics.setQuality('minimal')">Min</button>
            </div>
            <div id="ergo-quality-auto" class="ergo-auto-indicator">Auto-adjusting for battery</div>
          </div>
          
          <div class="ergo-section">
            <div class="ergo-stats">
              <div>Audio chunks: <span id="ergo-audio-count">0</span></div>
              <div>Frames: <span id="egro-frame-count">0</span></div>
              <div>Uptime: <span id="ergo-uptime">0:00</span></div>
            </div>
          </div>
        </div>
      `;

      // Add styles
      const style = document.createElement('style');
      style.textContent = `
        .sensor-ergonomics-panel {
          position: fixed;
          bottom: 20px;
          right: 20px;
          width: 280px;
          background: rgba(10, 24, 38, 0.95);
          border: 1px solid rgba(143, 173, 209, 0.2);
          border-radius: 12px;
          padding: 16px;
          color: #edf5ff;
          font-family: system-ui, -apple-system, sans-serif;
          font-size: 14px;
          z-index: 1000;
          backdrop-filter: blur(10px);
        }
        .ergo-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }
        .ergo-title {
          font-weight: 600;
          color: #5be0ce;
        }
        .ergo-toggle {
          background: transparent;
          border: none;
          color: #8ca2be;
          cursor: pointer;
          font-size: 18px;
        }
        .ergo-section {
          margin-bottom: 16px;
          padding-bottom: 12px;
          border-bottom: 1px solid rgba(143, 173, 209, 0.1);
        }
        .ergo-section:last-child {
          border-bottom: none;
          margin-bottom: 0;
        }
        .ergo-label {
          font-size: 12px;
          text-transform: uppercase;
          color: #8ca2be;
          margin-bottom: 8px;
        }
        .ergo-battery-display {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .ergo-battery-bar {
          flex: 1;
          height: 8px;
          background: rgba(143, 173, 209, 0.2);
          border-radius: 4px;
          overflow: hidden;
        }
        .ergo-battery-fill {
          height: 100%;
          background: #5be0ce;
          transition: width 0.3s, background 0.3s;
        }
        .ergo-battery-fill.low { background: #fbbf24; }
        .ergo-battery-fill.critical { background: #f87171; }
        .ergo-warning {
          margin-top: 8px;
          padding: 8px;
          background: rgba(248, 113, 113, 0.2);
          border-radius: 6px;
          font-size: 12px;
          color: #f87171;
        }
        .ergo-health-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
        }
        .ergo-health-item {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 13px;
        }
        .ergo-health-indicator {
          font-size: 10px;
        }
        .ergo-health-indicator.healthy { color: #2dd4bf; }
        .ergo-health-indicator.warning { color: #fbbf24; }
        .ergo-health-indicator.error { color: #f87171; }
        .ergo-quality-buttons {
          display: flex;
          gap: 4px;
        }
        .ergo-quality-btn {
          flex: 1;
          padding: 6px 4px;
          background: rgba(143, 173, 209, 0.1);
          border: 1px solid rgba(143, 173, 209, 0.2);
          border-radius: 4px;
          color: #edf5ff;
          cursor: pointer;
          font-size: 12px;
        }
        .ergo-quality-btn:hover {
          background: rgba(91, 224, 206, 0.2);
        }
        .ergo-quality-btn.active {
          background: #5be0ce;
          color: #07101b;
          border-color: #5be0ce;
        }
        .ergo-auto-indicator {
          margin-top: 8px;
          font-size: 11px;
          color: #fbbf24;
          font-style: italic;
        }
        .ergo-stats {
          font-size: 12px;
          color: #8ca2be;
        }
        .ergo-stats div {
          margin-bottom: 4px;
        }
        .ergo-collapsed .ergo-content {
          display: none;
        }
      `;

      document.head.appendChild(style);
      document.body.appendChild(panel);
      
      // Store UI references
      this.ui = {
        panel,
        batteryLevel: document.getElementById('ergo-battery-level'),
        batteryFill: document.getElementById('ergo-battery-fill'),
        batteryDrain: document.getElementById('ergo-battery-drain'),
        batteryWarning: document.getElementById('ergo-battery-warning'),
        audioIndicator: document.getElementById('ergo-audio-indicator'),
        audioStatus: document.getElementById('ergo-audio-status'),
        videoIndicator: document.getElementById('ergo-video-indicator'),
        videoStatus: document.getElementById('ergo-video-status'),
        qualityAuto: document.getElementById('ergo-quality-auto'),
        audioCount: document.getElementById('ergo-audio-count'),
        frameCount: document.getElementById('egro-frame-count'),
        uptime: document.getElementById('ergo-uptime'),
      };

      this.updateQualityDisplay();
    },

    /**
     * Toggle panel visibility
     */
    togglePanel() {
      const panel = document.getElementById('sensor-ergonomics-panel');
      if (panel) {
        panel.classList.toggle('ergo-collapsed');
      }
    },

    /**
     * Update battery display
     */
    updateBatteryDisplay() {
      if (!this.ui.batteryLevel) return;

      const level = this.state.battery?.level ?? null;
      const charging = this.state.battery?.charging ?? false;
      
      if (level !== null) {
        const percent = Math.round(level * 100);
        this.ui.batteryLevel.textContent = `${percent}%${charging ? ' ⚡' : ''}`;
        this.ui.batteryFill.style.width = `${percent}%`;
        
        // Color based on level
        this.ui.batteryFill.className = 'ergo-battery-fill';
        if (percent <= 15) this.ui.batteryFill.classList.add('critical');
        else if (percent <= 30) this.ui.batteryFill.classList.add('low');
      }

      // Update drain rate
      if (this.state.stats.estimatedBatteryCost > 0) {
        this.ui.batteryDrain.textContent = `${this.state.stats.estimatedBatteryCost.toFixed(1)}%/hr`;
      }
    },

    /**
     * Update health display
     */
    updateHealthDisplay() {
      if (!this.ui.audioStatus) return;

      const audio = this.state.streamHealth.audio;
      const video = this.state.streamHealth.video;

      // Audio status
      this.ui.audioStatus.textContent = audio.status === 'healthy' ? 'Good' : 
                                        audio.status === 'stalled' ? 'Stalled' : 'Unknown';
      this.ui.audioIndicator.className = 'ergo-health-indicator ' + 
        (audio.status === 'healthy' ? 'healthy' : 
         audio.status === 'stalled' ? 'error' : 'warning');

      // Video status
      this.ui.videoStatus.textContent = video.status === 'healthy' ? 'Good' : 
                                        video.status === 'stalled' ? 'Stalled' : 'Unknown';
      this.ui.videoIndicator.className = 'ergo-health-indicator ' + 
        (video.status === 'healthy' ? 'healthy' : 
         video.status === 'stalled' ? 'error' : 'warning');
    },

    /**
     * Update quality display
     */
    updateQualityDisplay() {
      // Update quality button states
      document.querySelectorAll('.ergo-quality-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.quality === this.state.currentQuality);
      });

      // Show/hide auto indicator
      if (this.ui.qualityAuto) {
        const isAuto = this.state.battery && !this.state.battery.charging;
        this.ui.qualityAuto.style.display = isAuto ? 'block' : 'none';
      }
    },

    /**
     * Update all UI elements
     */
    updateUI() {
      this.updateBatteryDisplay();
      this.updateHealthDisplay();
      this.updateQualityDisplay();
      
      // Update stats
      if (this.ui.audioCount) {
        this.ui.audioCount.textContent = this.state.stats.totalAudioChunks;
      }
      if (this.ui.frameCount) {
        this.ui.frameCount.textContent = this.state.stats.totalFrames;
      }
      if (this.ui.uptime && this.state.stats.startTime) {
        const uptime = Math.floor((Date.now() - this.state.stats.startTime) / 1000);
        const mins = Math.floor(uptime / 60);
        const secs = uptime % 60;
        this.ui.uptime.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
      }
    },

    /**
     * Show warning message
     */
    showWarning(message) {
      if (this.ui.batteryWarning) {
        this.ui.batteryWarning.textContent = message;
        this.ui.batteryWarning.style.display = 'block';
      }
    },

    /**
     * Show notification
     */
    showNotification(message) {
      // Could integrate with toast system
      console.log(`[SensorErgonomics] ${message}`);
    },
  };

  // Expose globally
  window.SensorErgonomics = SensorErgonomics;

  // Auto-init on load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => SensorErgonomics.init());
  } else {
    SensorErgonomics.init();
  }
})();
