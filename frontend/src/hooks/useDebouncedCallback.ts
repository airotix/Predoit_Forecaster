"use client";

import { useCallback, useRef } from "react";

/**
 * Returns a callback that invokes fn only after `delay` ms have passed
 * since the last call. Used to debounce search input.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function useDebouncedCallback<T extends (...args: any[]) => void>(
    fn: T,
    delay: number
): T {
    const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const fnRef = useRef(fn);
    fnRef.current = fn;

    const debounced = useCallback(
        (...args: Parameters<T>) => {
            if (timeoutRef.current) clearTimeout(timeoutRef.current);
            timeoutRef.current = setTimeout(() => {
                timeoutRef.current = null;
                fnRef.current(...args);
            }, delay);
        },
        [delay]
    ) as T;

    return debounced;
}
