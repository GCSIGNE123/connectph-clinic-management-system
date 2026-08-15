import { afterEach, describe, expect, it, vi } from "vitest";
import { getApiBaseUrl } from "./api-url";

function setLocation(href: string) {
  const url = new URL(href);
  Object.defineProperty(window, "location", {
    value: {
      protocol: url.protocol,
      hostname: url.hostname,
      port: url.port,
      href: url.href,
    },
    writable: true,
    configurable: true,
  });
}

describe("getApiBaseUrl", () => {
  const originalLocation = window.location;

  afterEach(() => {
    vi.unstubAllEnvs();
    Object.defineProperty(window, "location", { value: originalLocation, writable: true, configurable: true });
  });

  it("substitutes the browser's own hostname when the configured API URL is localhost", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:9000/api/v1");
    setLocation("http://localhost:3000/services");
    expect(getApiBaseUrl()).toBe("http://localhost:9000/api/v1");
  });

  it("substitutes the browser's own LAN hostname when the page was loaded via a LAN IP", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://192.168.68.114:9000/api/v1");
    setLocation("http://localhost:3000/services");
    expect(getApiBaseUrl()).toBe("http://localhost:9000/api/v1");
  });

  it("follows the page to a LAN IP even though the configured URL is a different LAN IP", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://192.168.68.114:9000/api/v1");
    setLocation("http://192.168.1.50:3000/services");
    expect(getApiBaseUrl()).toBe("http://192.168.1.50:9000/api/v1");
  });

  it("does not substitute a real (non-local) production API domain", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.connectph.example.com/api/v1");
    setLocation("https://app.connectph.example.com/services");
    expect(getApiBaseUrl()).toBe("https://api.connectph.example.com/api/v1");
  });

  it("falls back to the default when NEXT_PUBLIC_API_URL is unset", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    setLocation("http://localhost:3000/services");
    expect(getApiBaseUrl()).toBe("http://localhost:8000/api/v1");
  });
});
