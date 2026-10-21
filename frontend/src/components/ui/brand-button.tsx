import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/** Pill button from the Preduit / Mergco design system (Button: primary, outline, light, dark). */
const brandButtonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-full border font-display font-medium transition-[background-color,transform] duration-150 ease-[cubic-bezier(.22,1,.36,1)] active:scale-[.98] disabled:pointer-events-none disabled:opacity-45 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "border-transparent bg-brand text-white hover:bg-brand-hover",
        outline: "border-border-strong bg-transparent text-fg-1 hover:bg-soft",
        light: "border-transparent bg-soft text-fg-1 hover:bg-line",
        dark: "border-transparent bg-fg-1 text-page hover:opacity-90",
      },
      size: {
        sm: "h-8 px-4 text-[13px] [&_svg]:h-4 [&_svg]:w-4",
        md: "h-11 px-6 text-[15px] [&_svg]:h-[18px] [&_svg]:w-[18px]",
        lg: "h-[52px] px-7 text-base [&_svg]:h-[19px] [&_svg]:w-[19px]",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  }
);

export interface BrandButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof brandButtonVariants> {
  asChild?: boolean;
}

const BrandButton = React.forwardRef<HTMLButtonElement, BrandButtonProps>(
  ({ className, variant, size, asChild = false, type, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        type={asChild ? undefined : type ?? "button"}
        className={cn(brandButtonVariants({ variant, size }), className)}
        {...props}
      />
    );
  }
);
BrandButton.displayName = "BrandButton";

export { BrandButton, brandButtonVariants };
