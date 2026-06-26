interface PageHeaderProps {
  title: string
  description?: string
}

export function PageHeader({ title, description }: PageHeaderProps) {
  return (
    <div className="mb-7">
      <h1 className="text-2xl font-bold tracking-tight text-fg">{title}</h1>
      {description ? <p className="mt-1.5 text-sm text-muted">{description}</p> : null}
    </div>
  )
}
