"use client";

import React, { useState, useRef, useEffect } from "react";
import { ChevronDown, Check } from "lucide-react";

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: (SelectOption | string)[];
  placeholder?: string;
  className?: string;
  size?: "sm" | "md";
  align?: "left" | "right";
}

export function Select({
  value,
  onChange,
  options,
  placeholder = "Select...",
  className = "",
  size = "sm",
  align = "left",
}: SelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [highlightedIndex, setHighlightedIndex] = useState<number>(-1);

  // Normalize options
  const normalizedOptions: SelectOption[] = options.map((opt) =>
    typeof opt === "string" ? { value: opt, label: opt } : opt,
  );

  const selectedOption = normalizedOptions.find((opt) => opt.value === value);

  // Close on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  // Keyboard navigation
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!isOpen) {
        if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
          if (containerRef.current?.contains(document.activeElement)) {
            e.preventDefault();
            setIsOpen(true);
            const selectedIdx = normalizedOptions.findIndex((o) => o.value === value);
            setHighlightedIndex(selectedIdx >= 0 ? selectedIdx : 0);
          }
        }
        return;
      }

      if (e.key === "Escape") {
        setIsOpen(false);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlightedIndex((prev) =>
          prev < normalizedOptions.length - 1 ? prev + 1 : 0
        );
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlightedIndex((prev) =>
          prev > 0 ? prev - 1 : normalizedOptions.length - 1
        );
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < normalizedOptions.length) {
          onChange(normalizedOptions[highlightedIndex].value);
          setIsOpen(false);
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, highlightedIndex, normalizedOptions, value, onChange]);

  return (
    <div ref={containerRef} className={`relative inline-block text-left ${className}`}>
      {/* Trigger Button */}
      <button
        type="button"
        onClick={() => {
          setIsOpen(!isOpen);
          const selectedIdx = normalizedOptions.findIndex((o) => o.value === value);
          setHighlightedIndex(selectedIdx >= 0 ? selectedIdx : 0);
        }}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        className={`w-full inline-flex items-center justify-between gap-2.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-[var(--fg)] font-medium transition-all hover:bg-[var(--surface-secondary)] hover:border-[var(--muted)]/50 focus:outline-hidden focus:ring-2 focus:ring-[var(--fg)]/10 shadow-xs cursor-pointer select-none ${
          size === "sm" ? "px-3 py-1.5 text-[12px] h-[34px]" : "px-3.5 py-2 text-xs h-[38px]"
        }`}
      >
        <span className="truncate font-medium">
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronDown
          className={`w-3.5 h-3.5 text-[var(--muted)] shrink-0 transition-transform duration-200 ease-out ${
            isOpen ? "rotate-180 text-[var(--fg)]" : ""
          }`}
        />
      </button>

      {/* Popover Dropdown Menu */}
      {isOpen && (
        <div
          role="listbox"
          className={`absolute ${
            align === "right" ? "right-0" : "left-0"
          } z-50 min-w-[145px] w-max max-w-sm mt-1 bg-[var(--surface)] border border-[var(--border)] rounded-xl shadow-xl shadow-black/8 dark:shadow-black/50 p-1 focus:outline-hidden animate-in fade-in zoom-in-95 duration-150`}
        >
          <div className="max-h-64 overflow-y-auto space-y-0.5">
            {normalizedOptions.map((opt, idx) => {
              const isSelected = opt.value === value;
              const isHighlighted = idx === highlightedIndex;
              return (
                <div
                  key={opt.value}
                  role="option"
                  aria-selected={isSelected}
                  onMouseEnter={() => setHighlightedIndex(idx)}
                  onClick={() => {
                    onChange(opt.value);
                    setIsOpen(false);
                  }}
                  className={`flex items-center justify-between gap-3 px-3 py-1.5 text-[12px] rounded-md transition-colors cursor-pointer select-none ${
                    isSelected
                      ? "text-[var(--fg)] font-semibold bg-[var(--surface-secondary)]/60"
                      : isHighlighted
                      ? "text-[var(--fg)] bg-[var(--surface-secondary)]"
                      : "text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--surface-secondary)]"
                  }`}
                >
                  <span className="truncate">{opt.label}</span>
                  {isSelected && (
                    <Check className="w-3.5 h-3.5 text-[var(--fg)] stroke-[2.5] shrink-0" />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
