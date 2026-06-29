import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  LabelHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react"
import { cn } from "@/lib/utils"

type ButtonVariant = "default" | "outline" | "ghost" | "destructive"

export function Button({
  className,
  variant = "default",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  const variants: Record<ButtonVariant, string> = {
    default: "bg-primary text-primary-foreground hover:opacity-90",
    outline: "border border-input bg-transparent hover:bg-accent",
    ghost: "hover:bg-accent",
    destructive: "bg-destructive text-destructive-foreground hover:opacity-90",
  }
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition disabled:opacity-50 disabled:pointer-events-none",
        variants[variant],
        className,
      )}
      {...props}
    />
  )
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring",
        className,
      )}
      {...props}
    />
  )
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "flex min-h-[80px] w-full rounded-md border border-input bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring",
        className,
      )}
      {...props}
    />
  )
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring",
        className,
      )}
      {...props}
    />
  )
}

export function Label({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-sm font-medium", className)} {...props} />
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-lg border bg-card text-card-foreground shadow-sm", className)}
      {...props}
    />
  )
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4 border-b", className)} {...props} />
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("font-semibold leading-none", className)} {...props} />
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4", className)} {...props} />
}

export function Badge({
  className,
  children,
}: {
  className?: string
  children: ReactNode
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
        className,
      )}
    >
      {children}
    </span>
  )
}
