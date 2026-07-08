import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from ..config import settings

class PDFService:
    def generate_report(self, meeting_data: dict, output_filename: str) -> str:
        """
        Generates a professional PDF report for the meeting.
        meeting_data should contain:
            - title
            - created_at (formatted string or datetime)
            - filename
            - transcript
            - summary_executive
            - summary_detailed
            - summary_highlights
            - sentiment_positive
            - sentiment_neutral
            - sentiment_negative
            - action_items (list of dicts)
            - decisions (list of dicts or strings)
        """
        output_path = os.path.join(settings.REPORT_DIR, output_filename)
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=54,
            leftMargin=54,
            topMargin=54,
            bottomMargin=54
        )

        styles = getSampleStyleSheet()
        
        # Define modern styles
        title_style = ParagraphStyle(
            name='ReportTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=24,
            leading=28,
            textColor=colors.HexColor('#1E293B'), # Slate 800
            spaceAfter=10
        )
        
        subtitle_style = ParagraphStyle(
            name='ReportSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#64748B'), # Slate 500
            spaceAfter=20
        )

        h1_style = ParagraphStyle(
            name='SectionHeader',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=14,
            leading=18,
            textColor=colors.HexColor('#0F172A'), # Slate 900
            spaceBefore=15,
            spaceAfter=8,
            keepWithNext=True
        )

        body_style = ParagraphStyle(
            name='ReportBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#334155'), # Slate 700
            spaceAfter=8
        )

        bold_body_style = ParagraphStyle(
            name='ReportBoldBody',
            parent=body_style,
            fontName='Helvetica-Bold'
        )

        bullet_style = ParagraphStyle(
            name='ReportBullet',
            parent=body_style,
            leftIndent=20,
            firstLineIndent=-10,
            spaceAfter=4
        )

        table_header_style = ParagraphStyle(
            name='TableHeader',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=11,
            textColor=colors.white
        )

        table_body_style = ParagraphStyle(
            name='TableBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#1E293B')
        )

        story = []

        # Header Title
        story.append(Paragraph("MeetingMind AI - Report Summary", title_style))
        story.append(Paragraph(f"Meeting Title: {meeting_data.get('title')}<br/>Date Generated: {meeting_data.get('created_at')}<br/>Audio File: {meeting_data.get('filename')}", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E2E8F0'), spaceAfter=15))

        # Sentiment Summary
        pos = int(meeting_data.get('sentiment_positive', 0.0) * 100)
        neu = int(meeting_data.get('sentiment_neutral', 0.0) * 100)
        neg = int(meeting_data.get('sentiment_negative', 0.0) * 100)
        sentiment_text = f"<b>Sentiment Distribution:</b> Positive: {pos}% | Neutral: {neu}% | Negative: {neg}%"
        story.append(Paragraph(sentiment_text, body_style))
        story.append(Spacer(1, 10))

        # Executive Summary
        story.append(Paragraph("Executive Summary", h1_style))
        story.append(Paragraph(meeting_data.get('summary_executive') or "No executive summary available.", body_style))
        story.append(Spacer(1, 10))

        # Detailed Summary & Highlights
        story.append(Paragraph("Detailed Summary", h1_style))
        story.append(Paragraph(meeting_data.get('summary_detailed') or "No detailed summary available.", body_style))
        story.append(Spacer(1, 10))

        if meeting_data.get('summary_highlights'):
            story.append(Paragraph("Discussion Highlights", h1_style))
            highlights = meeting_data.get('summary_highlights').split('\n')
            for highlight in highlights:
                if highlight.strip():
                    story.append(Paragraph(highlight.strip(), bullet_style))
            story.append(Spacer(1, 10))

        # Action Items Table
        story.append(Paragraph("Action Items", h1_style))
        actions = meeting_data.get('action_items', [])
        if actions:
            # Table columns: Task, Owner, Deadline, Priority, Status
            data = [[
                Paragraph("Task", table_header_style),
                Paragraph("Owner", table_header_style),
                Paragraph("Deadline", table_header_style),
                Paragraph("Priority", table_header_style),
                Paragraph("Status", table_header_style)
            ]]
            for act in actions:
                data.append([
                    Paragraph(act.get('task', ''), table_body_style),
                    Paragraph(act.get('owner', 'Unassigned'), table_body_style),
                    Paragraph(act.get('deadline', 'N/A') or 'N/A', table_body_style),
                    Paragraph(act.get('priority', 'Medium'), table_body_style),
                    Paragraph(act.get('status', 'Pending'), table_body_style)
                ])
            
            # Width calculation (total = 504 pt for letter size margins)
            t = Table(data, colWidths=[200, 75, 75, 74, 80])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ]))
            story.append(t)
        else:
            story.append(Paragraph("No action items extracted.", body_style))
        story.append(Spacer(1, 15))

        # Decisions
        story.append(Paragraph("Key Decisions & Risks", h1_style))
        decisions = meeting_data.get('decisions', [])
        if decisions:
            story.append(Paragraph("<b>Decisions Made:</b>", bold_body_style))
            for dec in decisions:
                text = dec.get('decision_text') if isinstance(dec, dict) else dec
                story.append(Paragraph(f"• {text}", bullet_style))
        else:
            story.append(Paragraph("No direct decisions documented.", body_style))
        story.append(Spacer(1, 10))

        # Transcript
        story.append(Paragraph("Full Meeting Transcript", h1_style))
        transcript_raw = meeting_data.get('transcript') or "No transcript available."
        # Format transcript lines
        lines = transcript_raw.split('\n')
        for line in lines:
            if line.strip():
                story.append(Paragraph(line.strip(), body_style))
        
        doc.build(story)
        return output_path

pdf_service = PDFService()
