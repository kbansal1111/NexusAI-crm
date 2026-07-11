"use client"

import * as React from "react"
import { Check, ChevronsUpDown, Loader2 } from "lucide-react"
import { useDebounce } from "@/hooks/use-debounce"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
} from "@/components/ui/command"
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover"

export interface SearchableSelectOption {
    label: string
    value: string
    disabled?: boolean
}

/**
 * Word-prefix matching for client-side filtering — the industry-standard
 * typeahead rule, same as the server's word_prefix_regex: "ja" matches
 * "Jaipur" and "New Jalpaiguri" but not "Andijan". Whole-label prefix
 * scores higher so it sorts first.
 */
function wordPrefixFilter(value: string, search: string, keywords?: string[]): number {
    const q = search.trim().toLowerCase()
    if (!q) return 1
    const label = (keywords?.[0] ?? value.split(":::")[0] ?? "").toLowerCase()
    if (label.startsWith(q)) return 2
    return label.split(/[^a-z0-9]+/).some((w) => w.startsWith(q)) ? 1 : 0
}

interface SearchableSelectProps {
    options: SearchableSelectOption[]
    value?: string
    onValueChange: (value: string) => void
    onSearch?: (query: string, signal?: AbortSignal) => void
    placeholder?: string
    searchPlaceholder?: string
    emptyMessage?: string
    disabled?: boolean
    isLoading?: boolean
    className?: string
}

export function SearchableSelect({
    options,
    value,
    onValueChange,
    onSearch,
    placeholder = "Select...",
    searchPlaceholder = "Search...",
    emptyMessage = "No results found.",
    disabled = false,
    isLoading = false,
    className
}: SearchableSelectProps) {
    const [open, setOpen] = React.useState(false)
    const [searchValue, setSearchValue] = React.useState("")
    const debouncedSearch = useDebounce(searchValue, 300)

    const onSearchRef = React.useRef(onSearch)
    React.useEffect(() => {
        onSearchRef.current = onSearch
    }, [onSearch])

    React.useEffect(() => {
        if (!onSearchRef.current) return

        const controller = new AbortController()
        onSearchRef.current(debouncedSearch, controller.signal)

        return () => {
            controller.abort()
        }
    }, [debouncedSearch])

    const selectedOption = React.useMemo(() => 
        options.find((opt) => opt.value === value),
    [options, value])

    return (
        // modal — without it, opening this inside a Radix Dialog leaves the
        // dialog's scroll-lock active over the portaled dropdown, so the
        // option list cannot be scrolled with the mouse wheel.
        <Popover open={open} onOpenChange={setOpen} modal={true}>
            <PopoverTrigger asChild>
                <Button
                    variant="outline"
                    role="combobox"
                    aria-expanded={open}
                    className={cn(
                        "h-8 w-full justify-between px-2 text-xs font-normal",
                        !value && "text-muted-foreground",
                        className
                    )}
                    disabled={disabled || isLoading}
                >
                    <span className="truncate">
                        {isLoading ? (
                            <span className="flex items-center gap-2">
                                <Loader2 className="h-3 w-3 animate-spin" />
                                Loading...
                            </span>
                        ) : (
                            selectedOption ? selectedOption.label : placeholder
                        )}
                    </span>
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
                <Command shouldFilter={!onSearch} filter={wordPrefixFilter}>
                    <CommandInput 
                        placeholder={searchPlaceholder} 
                        className="h-9" 
                        value={searchValue}
                        onValueChange={setSearchValue}
                    />
                    <CommandList>
                        {isLoading ? (
                            <div className="flex items-center justify-center py-6 text-sm text-muted-foreground">
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Searching...
                            </div>
                        ) : (
                            <>
                                <CommandEmpty>{emptyMessage}</CommandEmpty>
                                <CommandGroup className="max-h-64 overflow-auto p-1">
                                    {Array.from(new Map(options.map(o => [o.value, o])).values()).map((option) => (
                                        <CommandItem
                                            key={option.value}
                                            value={`${option.label}:::${option.value}`} // Include label for better cmdk matching
                                            keywords={[option.label, option.value]} // Additional search keywords
                                            onSelect={() => {
                                                if (option.disabled) return
                                                onValueChange(option.value === value ? "" : option.value)
                                                setOpen(false)
                                            }}
                                            disabled={option.disabled}
                                            className={cn(
                                                "flex items-center justify-between py-2 px-2",
                                                option.disabled && "opacity-50 cursor-not-allowed"
                                            )}
                                        >
                                            <div className="flex items-center gap-2 truncate">
                                                <Check
                                                    className={cn(
                                                        "h-4 w-4 text-primary",
                                                        value === option.value ? "opacity-100" : "opacity-0"
                                                    )}
                                                />
                                                <span className="truncate">{option.label}</span>
                                            </div>
                                        </CommandItem>
                                    ))}
                                </CommandGroup>
                            </>
                        )}
                    </CommandList>
                </Command>
            </PopoverContent>
        </Popover>
    )
}
