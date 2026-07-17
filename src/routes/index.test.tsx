import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { ComponentType } from "react";
import { DataProvider } from "@/lib/data-store";
import { ThemeProvider } from "@/lib/theme";
import { Route as LandingRoute } from "./index";

const LandingPage = LandingRoute.options.component as ComponentType;

function renderLanding() {
  return render(
    <ThemeProvider>
      <DataProvider>
        <LandingPage />
      </DataProvider>
    </ThemeProvider>,
  );
}

describe("landing-page theme toggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  it("renders the current theme icon and updates the document, label, icon, and storage", async () => {
    localStorage.setItem("theme", "dark");
    const user = userEvent.setup();
    renderLanding();

    await waitFor(() => expect(document.documentElement).toHaveClass("dark"));
    const darkModeToggle = screen.getByRole("button", { name: "Switch to light mode" });
    expect(darkModeToggle.querySelector(".lucide-sun")).toBeInTheDocument();
    expect(darkModeToggle.querySelector(".lucide-moon")).not.toBeInTheDocument();

    await user.click(darkModeToggle);

    await waitFor(() => expect(document.documentElement).not.toHaveClass("dark"));
    const lightModeToggle = screen.getByRole("button", { name: "Switch to dark mode" });
    expect(lightModeToggle.querySelector(".lucide-moon")).toBeInTheDocument();
    expect(lightModeToggle.querySelector(".lucide-sun")).not.toBeInTheDocument();
    expect(localStorage.getItem("theme")).toBe("light");
  });
});
