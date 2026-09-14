import { useState } from 'react'
import { Mail, MessageSquare, Clock, AlertTriangle, CheckCircle2, Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { useUser } from '@/lib/user-context'

type SubmitStatus = 'idle' | 'submitting' | 'success' | 'error'

export default function Support() {
  const user = useUser()
  const [status, setStatus] = useState<SubmitStatus>('idle')
  const [form, setForm] = useState({
    name: user.name,
    email: user.email,
    product: 'general',
    subject: '',
    body: '',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setStatus('submitting')
    // Stub: backend ticket integration deferred
    setTimeout(() => setStatus('success'), 800)
  }

  return (
    <section className="container py-12 animate-card-rise">
      {/* Page header */}
      <div className="mb-10">
        <p className="font-nav text-[13px] font-medium uppercase tracking-[0.15em] text-muted-foreground mb-2">
          Support
        </p>
        <h1 className="font-display text-4xl md:text-5xl font-light text-primary leading-tight">
          We're here to help.
        </h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Ticket form */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Submit a ticket</CardTitle>
              <CardDescription>
                Describe the issue and we'll get back to you as soon as possible.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {status === 'success' ? (
                <div className="flex flex-col items-center py-8 gap-3 text-center">
                  <CheckCircle2 className="h-10 w-10 text-tier-green-base" />
                  <p className="font-semibold text-foreground">Ticket submitted</p>
                  <p className="text-sm text-muted-foreground">
                    We'll follow up at {form.email}.
                  </p>
                  <Button
                    variant="outline"
                    className="mt-4"
                    onClick={() => {
                      setStatus('idle')
                      setForm(f => ({ ...f, subject: '', body: '' }))
                    }}
                  >
                    Submit another
                  </Button>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-5">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                    <div className="space-y-2">
                      <Label htmlFor="name">Name</Label>
                      <Input
                        id="name"
                        value={form.name}
                        onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="email">Email</Label>
                      <Input
                        id="email"
                        type="email"
                        value={form.email}
                        onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="product">Product</Label>
                    <select
                      id="product"
                      value={form.product}
                      onChange={e => setForm(f => ({ ...f, product: e.target.value }))}
                      className="flex h-11 w-full rounded-md border border-input bg-background px-4 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    >
                      <option value="general">General</option>
                      <option value="structured">Structured (ARC)</option>
                      <option value="unstructured">Unstructured (PrimeData)</option>
                    </select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="subject">Subject</Label>
                    <Input
                      id="subject"
                      placeholder="Brief summary of the issue"
                      value={form.subject}
                      onChange={e => setForm(f => ({ ...f, subject: e.target.value }))}
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="body">Description</Label>
                    <Textarea
                      id="body"
                      placeholder="What happened? What did you expect? Steps to reproduce..."
                      value={form.body}
                      onChange={e => setForm(f => ({ ...f, body: e.target.value }))}
                      required
                    />
                  </div>

                  <Button
                    type="submit"
                    disabled={status === 'submitting'}
                    className="gap-2"
                  >
                    <Send className="h-4 w-4" />
                    {status === 'submitting' ? 'Submitting...' : 'Submit ticket'}
                  </Button>
                </form>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Contact sidebar */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Contact</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <ContactItem icon={Mail} label="Email" value="primexarc@lilly.com" />
              <ContactItem icon={MessageSquare} label="Slack" value="#primexarc-support" />
              <ContactItem icon={Clock} label="Hours" value="Mon-Fri, 9am-5pm EST" />
            </CardContent>
          </Card>

          <Card className="border-tier-amber-base/30 bg-tier-amber-light/30">
            <CardContent className="pt-6">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 text-tier-amber-base flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-sm text-foreground mb-1">Urgent issue?</p>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    For production-impacting incidents, contact the on-call team via PagerDuty
                    or the Slack escalation channel.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  )
}

function ContactItem({ icon: Icon, label, value }: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
}) {
  return (
    <div className="flex items-center gap-3">
      <Icon className="h-4 w-4 text-muted-foreground" />
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-sm font-medium text-foreground">{value}</p>
      </div>
    </div>
  )
}
