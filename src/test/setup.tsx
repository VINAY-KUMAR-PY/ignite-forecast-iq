import "@testing-library/jest-dom/vitest";
import React from "react";
import { vi } from "vitest";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
  createRootRouteWithContext: () => (options: unknown) => ({ options }),
  Outlet: () => null,
  useLocation: () => ({ pathname: "/app" }),
  useRouter: () => ({ navigate: vi.fn() }),
  Link: ({
    children,
    to,
    onClick,
    className,
  }: {
    children: React.ReactNode;
    to?: string;
    onClick?: () => void;
    className?: string;
  }) => (
    <a
      href={to ?? "#"}
      className={className}
      onClick={(event) => {
        event.preventDefault();
        onClick?.();
      }}
    >
      {children}
    </a>
  ),
}));

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(window, "ResizeObserver", {
  writable: true,
  configurable: true,
  value: ResizeObserverMock,
});

Object.defineProperty(window, "matchMedia", {
  writable: true,
  configurable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

HTMLElement.prototype.scrollIntoView = vi.fn();
HTMLElement.prototype.hasPointerCapture = vi.fn();
HTMLElement.prototype.releasePointerCapture = vi.fn();
