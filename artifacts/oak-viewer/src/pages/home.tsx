import React, { useState, useEffect, useRef } from "react";
import { Camera, RefreshCw, Activity, AlertTriangle, Settings2, TerminalSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type StreamStatus = "idle" | "connecting" | "streaming" | "error";

export default function Home() {
  const [streamUrl, setStreamUrl] = useState(() => {
    return localStorage.getItem("oakStreamUrl") || "http://localhost:8083/stream";
  });
  
  const [activeUrl, setActiveUrl] = useState("");
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [cacheBust, setCacheBust] = useState(Date.now());
  const [configOpen, setConfigOpen] = useState(false);
  
  const imageRef = useRef<HTMLImageElement>(null);

  // Initialize stream on mount
  useEffect(() => {
    handleConnect();
  }, []);

  const handleConnect = () => {
    if (!streamUrl.trim()) return;
    
    // Save to local storage
    localStorage.setItem("oakStreamUrl", streamUrl);
    
    setStatus("connecting");
    setCacheBust(Date.now());
    
    const url = new URL(streamUrl);
    url.searchParams.set("t", Date.now().toString());
    setActiveUrl(url.toString());
  };

  const handleReconnect = () => {
    handleConnect();
  };

  const onStreamLoad = () => {
    setStatus("streaming");
  };

  const onStreamError = () => {
    setStatus("error");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleConnect();
    }
  };

  return (
    <div className="flex flex-col h-screen w-full bg-background overflow-hidden selection:bg-primary/30">
      {/* Header */}
      <header className="flex-none h-14 border-b border-border bg-card/50 backdrop-blur flex items-center justify-between px-4 z-10">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 rounded bg-primary/10 text-primary border border-primary/20">
            <Camera className="w-4 h-4" />
          </div>
          <div>
            <h1 className="text-sm font-semibold tracking-tight uppercase text-foreground/90">OAK-4 Monitor</h1>
            <p className="text-[10px] text-muted-foreground uppercase font-mono tracking-wider">Live Feed</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Status Indicator */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-secondary border border-border">
            <div className="relative flex items-center justify-center">
              {status === "connecting" && (
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-500 animate-pulse" />
              )}
              {status === "streaming" && (
                <>
                  <div className="w-2.5 h-2.5 rounded-full bg-success absolute animate-ping opacity-75" />
                  <div className="w-2.5 h-2.5 rounded-full bg-success relative" />
                </>
              )}
              {status === "error" && (
                <div className="w-2.5 h-2.5 rounded-full bg-destructive" />
              )}
              {status === "idle" && (
                <div className="w-2.5 h-2.5 rounded-full bg-muted-foreground" />
              )}
            </div>
            <span className="text-xs font-mono uppercase tracking-wider text-muted-foreground">
              {status}
            </span>
          </div>

          <Button 
            variant="outline" 
            size="sm" 
            onClick={() => setConfigOpen(!configOpen)}
            className="h-8 border-border bg-transparent text-muted-foreground hover:text-foreground"
            data-testid="button-toggle-config"
          >
            <Settings2 className="w-4 h-4 mr-2" />
            Config
          </Button>

          <Button 
            variant="default" 
            size="sm" 
            onClick={handleReconnect}
            className="h-8 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold uppercase tracking-wider text-xs px-4"
            data-testid="button-reconnect"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-2 ${status === "connecting" ? "animate-spin" : ""}`} />
            Reconnect
          </Button>
        </div>
      </header>

      {/* Config Panel */}
      {configOpen && (
        <div className="flex-none border-b border-border bg-card p-4 shadow-xl z-20 animate-in slide-in-from-top-2 duration-200">
          <div className="max-w-3xl mx-auto flex items-end gap-3">
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="stream-url" className="text-xs uppercase font-mono tracking-wider text-muted-foreground">Stream URL</Label>
              <div className="relative">
                <TerminalSquare className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input 
                  id="stream-url"
                  value={streamUrl}
                  onChange={(e) => setStreamUrl(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className="pl-9 font-mono text-sm h-10 bg-background/50 border-border focus-visible:ring-primary/50"
                  placeholder="http://localhost:8083/stream"
                  data-testid="input-stream-url"
                />
              </div>
            </div>
            <Button 
              onClick={handleConnect} 
              className="h-10 px-6 font-mono text-xs uppercase tracking-wider"
              data-testid="button-apply-config"
            >
              Apply
            </Button>
          </div>
        </div>
      )}

      {/* Main Viewer Area */}
      <main className="flex-1 relative bg-black flex items-center justify-center overflow-hidden">
        
        {/* Background Grid Pattern for Technical Feel */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:40px_40px] pointer-events-none" />
        
        {/* Crosshair Overlay */}
        <div className="absolute inset-0 pointer-events-none flex items-center justify-center opacity-10">
          <div className="w-[1px] h-full bg-primary" />
          <div className="h-[1px] w-full bg-primary absolute" />
          <div className="w-16 h-16 border border-primary rounded-full absolute" />
        </div>

        {/* Video Feed */}
        <div className="relative w-full h-full flex items-center justify-center p-4">
          {activeUrl ? (
            <div className="relative w-full h-full max-w-[1920px] max-h-[1080px] flex items-center justify-center border border-border/50 bg-card/20 shadow-2xl overflow-hidden rounded-sm">
              <img
                ref={imageRef}
                src={activeUrl}
                alt="OAK-4 MJPEG Stream"
                onLoad={onStreamLoad}
                onError={onStreamError}
                className={`max-w-full max-h-full object-contain transition-opacity duration-300 ${status === "streaming" ? "opacity-100" : "opacity-30 blur-sm"}`}
                data-testid="img-stream"
              />
              
              {/* Overlays for different states */}
              {status === "connecting" && (
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60 backdrop-blur-sm z-10">
                  <Activity className="w-12 h-12 text-primary animate-pulse mb-4" />
                  <p className="text-primary font-mono text-sm uppercase tracking-widest">Connecting to Stream...</p>
                  <p className="text-muted-foreground font-mono text-xs mt-2">{streamUrl}</p>
                </div>
              )}
              
              {status === "error" && (
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 backdrop-blur-sm z-10 border border-destructive/20">
                  <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
                    <AlertTriangle className="w-8 h-8 text-destructive" />
                  </div>
                  <p className="text-destructive font-mono text-sm uppercase tracking-widest font-bold">Connection Failed</p>
                  <p className="text-muted-foreground font-mono text-xs mt-2 max-w-md text-center">
                    Unable to load MJPEG stream from {streamUrl}. Verify the Python server is running and the URL is correct.
                  </p>
                  <Button 
                    variant="outline" 
                    onClick={handleReconnect}
                    className="mt-6 border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive"
                    data-testid="button-error-reconnect"
                  >
                    <RefreshCw className="w-4 h-4 mr-2" />
                    Retry Connection
                  </Button>
                </div>
              )}
              
              {/* Telemetry Overlay (Mock) */}
              {status === "streaming" && (
                <div className="absolute top-4 left-4 pointer-events-none">
                  <div className="bg-black/50 backdrop-blur border border-primary/20 p-2 rounded text-[10px] font-mono text-primary/80 uppercase tracking-widest">
                    <div className="flex items-center gap-2 mb-1">
                      <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                      LIVE / OAK-4
                    </div>
                    <div className="text-muted-foreground">FPS: --</div>
                    <div className="text-muted-foreground">RES: AUTO</div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center text-muted-foreground h-full w-full border border-dashed border-border/50 rounded bg-card/10">
              <Camera className="w-12 h-12 mb-4 opacity-20" />
              <p className="font-mono text-sm uppercase tracking-widest">No Stream Configured</p>
            </div>
          )}
        </div>
      </main>
      
      {/* Footer / Status bar */}
      <footer className="flex-none h-8 border-t border-border bg-card/80 flex items-center justify-between px-4">
        <div className="flex items-center gap-4 text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          <span>Target: {streamUrl}</span>
        </div>
        <div className="flex items-center gap-4 text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          <span>Engine: MJPEG</span>
          <span>Sys: Ready</span>
        </div>
      </footer>
    </div>
  );
}
