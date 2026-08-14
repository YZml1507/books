"use client";

import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/lib/store";

export function ThemeSwitch() {
  const theme = useAppStore((state) => state.theme);
  const setTheme = useAppStore((state) => state.setTheme);
  const isLight = theme === "light";

  return (
    <Button
      aria-label={isLight ? "切换深色模式" : "切换浅色模式"}
      size="icon"
      variant="outline"
      onClick={() => setTheme(isLight ? "dark" : "light")}
      title={isLight ? "切换深色模式" : "切换浅色模式"}
    >
      {isLight ? <Moon className="size-4" /> : <Sun className="size-4" />}
    </Button>
  );
}
