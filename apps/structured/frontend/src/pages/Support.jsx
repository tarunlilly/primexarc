import { useState } from 'react';
import { Mail, MessageSquare, Clock, Activity, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { api } from '@/lib/api';

export default function Support() {
  const [form, setForm] = useState({ name: '', email: '', subject: '', body: '' });
  const [status, setStatus] = useState(null); // null | 'sending' | 'sent' | 'stub'

  const update = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  async function submit() {
    setStatus('sending');
    try {
      await api.submitTicket(form);
      setStatus('sent');
    } catch {
      setStatus('stub');
    }
  }

  return (
    <section className="container py-16">
      <div className="max-w-5xl mx-auto">
        <header className="text-center mb-12">
          <p className="font-nav text-[14px] font-medium text-primary mb-4">
            Support
          </p>
          <h1 className="font-display text-5xl md:text-6xl font-light text-primary tracking-tight">
            How can we help?
          </h1>
          <p className="mt-6 text-lg text-muted-foreground max-w-xl mx-auto">
            Bug reports, feature requests, questions about a dimension score -
            all welcome. We aim to respond within one business day.
          </p>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <TicketForm
            form={form}
            update={update}
            submit={submit}
            status={status}
          />
          <ContactCard />
        </div>
      </div>
    </section>
  );
}

// ─── Ticket form ───────────────────────────────────────────────────────────
function TicketForm({ form, update, submit, status }) {
  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle className="font-display text-2xl font-normal">
          Open a ticket
        </CardTitle>
        <CardDescription>
          All fields are required. Tickets are routed to the AI Readiness team.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field id="name" label="Your name">
            <Input id="name" value={form.name} onChange={update('name')} />
          </Field>
          <Field id="email" label="Lilly email">
            <Input
              id="email"
              type="email"
              value={form.email}
              onChange={update('email')}
              placeholder="username@lilly.com"
            />
          </Field>
        </div>

        <Field id="subject" label="Subject">
          <Input id="subject" value={form.subject} onChange={update('subject')} />
        </Field>

        <Field id="body" label="Describe the issue">
          <Textarea
            id="body"
            value={form.body}
            onChange={update('body')}
            className="min-h-[160px]"
          />
        </Field>

        <div className="flex items-center gap-4 flex-wrap pt-2">
          <Button onClick={submit} disabled={status === 'sending'}>
            {status === 'sending' ? 'Sending…' : 'Submit Ticket'}
          </Button>
          {status === 'stub' && (
            <p className="text-xs text-muted-foreground flex items-center gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5" />
              Backend ticket route not yet wired - message captured client-side only.
            </p>
          )}
          {status === 'sent' && (
            <p className="text-xs font-semibold text-tier-green-base flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5" />
              Ticket received - check your inbox.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Contact card ──────────────────────────────────────────────────────────
function ContactCard() {
  const rows = [
    { icon: Mail, label: 'Email', value: 'ai-readiness@lilly.com', href: 'mailto:ai-readiness@lilly.com' },
    { icon: MessageSquare, label: 'Slack', value: '#ai-readiness-evaluator' },
    { icon: Clock, label: 'Hours', value: 'Mon–Fri · 8a–6p ET' },
    { icon: Activity, label: 'Status', value: 'status.internal.lilly.com' },
  ];
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="font-display text-lg font-normal">
            Other channels
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {rows.map((r) => {
            const Icon = r.icon;
            return (
              <div key={r.label} className="flex items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted text-primary">
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    {r.label}
                  </p>
                  {r.href ? (
                    <a
                      href={r.href}
                      className="text-sm font-semibold text-foreground hover:text-primary truncate block"
                    >
                      {r.value}
                    </a>
                  ) : (
                    <p className="text-sm font-semibold text-foreground truncate">
                      {r.value}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      <Card className="border-tier-red-base/30 bg-tier-red-light/40">
        <CardContent className="p-5 flex gap-3">
          <AlertTriangle className="h-5 w-5 text-tier-red-base shrink-0 mt-0.5" />
          <p className="text-xs text-foreground leading-relaxed">
            For urgent production issues affecting a regulated workflow, page
            the on-call via PagerDuty - do not file a ticket.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Helper ────────────────────────────────────────────────────────────────
function Field({ id, label, children }) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
